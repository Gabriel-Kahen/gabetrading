from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math

import pandas as pd
import yfinance as yf

from app.config import settings

try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestBarRequest
except Exception:  # pragma: no cover
    StockHistoricalDataClient = None
    StockLatestBarRequest = None


@dataclass
class MarketSnapshot:
    prices: dict[str, float]
    history: pd.DataFrame
    intraday_history: pd.DataFrame


class MarketDataService:
    def __init__(self) -> None:
        self._alpaca_client = None
        self._cached_daily_history = pd.DataFrame()
        self._daily_history_expires_at: datetime | None = None
        if settings.alpaca_api_key and settings.alpaca_secret_key and StockHistoricalDataClient:
            self._alpaca_client = StockHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_secret_key)

    def fetch_snapshot(self, symbols: list[str]) -> MarketSnapshot:
        history = self._daily_history(symbols)
        intraday_history = _download_prices(
            tickers=symbols,
            period=f"{settings.intraday_lookback_days}d",
            interval=settings.intraday_interval,
            auto_adjust=True,
            prepost=False,
            progress=False,
            group_by="ticker",
            threads=True,
        )

        prices = self._extract_latest_prices(symbols, intraday_history)
        if self._alpaca_client:
            prices.update(self._fetch_alpaca_latest_prices(symbols, self._latest_timestamp(intraday_history)))

        return MarketSnapshot(prices=prices, history=history, intraday_history=intraday_history)

    def _daily_history(self, symbols: list[str]) -> pd.DataFrame:
        now = datetime.now(timezone.utc)
        if self._daily_history_expires_at and now < self._daily_history_expires_at and not self._cached_daily_history.empty:
            return self._cached_daily_history

        period_days = max(settings.lookback_days + 20, 120)
        start = now - timedelta(days=period_days)
        history = _download_prices(
            tickers=symbols,
            start=start.date().isoformat(),
            end=now.date().isoformat(),
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="ticker",
            threads=True,
        )
        self._cached_daily_history = history
        self._daily_history_expires_at = now + timedelta(seconds=settings.daily_history_refresh_seconds)
        return history

    def _extract_latest_prices(self, symbols: list[str], history: pd.DataFrame) -> dict[str, float]:
        prices: dict[str, float] = {}
        if history.empty:
            return prices

        multi_symbol = isinstance(history.columns, pd.MultiIndex)
        latest_batch_timestamp = self._latest_timestamp(history)
        max_staleness = self._max_bar_staleness()
        if self._is_stale_bar(latest_batch_timestamp, pd.Timestamp(self._now()), max_staleness):
            return prices
        for symbol in symbols:
            try:
                if multi_symbol:
                    close_series = history[symbol]["Close"].dropna()
                else:
                    close_series = history["Close"].dropna()
                if not close_series.empty:
                    latest_symbol_timestamp = close_series.index[-1]
                    if self._is_stale_bar(latest_symbol_timestamp, latest_batch_timestamp, max_staleness):
                        continue
                    price = float(close_series.iloc[-1])
                    if self._is_valid_price(price):
                        prices[symbol] = price
            except Exception:
                continue
        return prices

    def _is_valid_price(self, price: float) -> bool:
        return math.isfinite(price) and price > 0.0

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _latest_timestamp(self, history: pd.DataFrame) -> pd.Timestamp | None:
        if history.empty or len(history.index) == 0:
            return None
        try:
            return pd.Timestamp(history.index.max())
        except Exception:
            return None

    def _max_bar_staleness(self) -> pd.Timedelta:
        try:
            interval = pd.Timedelta(settings.intraday_interval)
        except ValueError:
            interval = pd.Timedelta(minutes=15)
        return max(interval * 3, pd.Timedelta(minutes=30))

    def _is_stale_bar(
        self,
        bar_timestamp: object,
        latest_batch_timestamp: pd.Timestamp | None,
        max_staleness: pd.Timedelta,
    ) -> bool:
        if latest_batch_timestamp is None:
            return False
        try:
            latest_symbol_timestamp = pd.Timestamp(bar_timestamp)
            latest_timestamp = pd.Timestamp(latest_batch_timestamp)
            if latest_symbol_timestamp.tzinfo is None and latest_timestamp.tzinfo is not None:
                latest_symbol_timestamp = latest_symbol_timestamp.tz_localize(latest_timestamp.tzinfo)
            elif latest_symbol_timestamp.tzinfo is not None and latest_timestamp.tzinfo is None:
                latest_timestamp = latest_timestamp.tz_localize(latest_symbol_timestamp.tzinfo)
            return latest_timestamp - latest_symbol_timestamp > max_staleness
        except Exception:
            return False

    def _fetch_alpaca_latest_prices(
        self,
        symbols: list[str],
        latest_batch_timestamp: pd.Timestamp | None = None,
    ) -> dict[str, float]:
        if not self._alpaca_client or not StockLatestBarRequest:
            return {}
        try:
            request = StockLatestBarRequest(symbol_or_symbols=symbols)
            bars = self._alpaca_client.get_stock_latest_bar(request)
            prices: dict[str, float] = {}
            comparison_timestamp = latest_batch_timestamp or pd.Timestamp(datetime.now(timezone.utc))
            max_staleness = self._max_bar_staleness()
            for symbol, bar in bars.items():
                price = getattr(bar, "close", None)
                timestamp = getattr(bar, "timestamp", None)
                if price is None or timestamp is None:
                    continue
                price = float(price)
                if not self._is_valid_price(price):
                    continue
                if self._is_stale_bar(timestamp, comparison_timestamp, max_staleness):
                    continue
                prices[symbol] = price
            return prices
        except Exception:
            return {}


def _download_prices(**kwargs) -> pd.DataFrame:
    kwargs["threads"] = False
    return yf.download(**kwargs)


def symbol_history_frame(history: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()
    if isinstance(history.columns, pd.MultiIndex):
        if symbol not in history.columns.get_level_values(0):
            return pd.DataFrame()
        frame = history[symbol].copy()
    else:
        frame = history.copy()
    frame.columns = [str(col).lower() for col in frame.columns]
    return frame.dropna(how="all")
