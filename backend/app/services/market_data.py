from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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
        if not prices:
            prices = self._extract_latest_prices(symbols, history)
        if self._alpaca_client:
            prices.update(self._fetch_alpaca_latest_prices(symbols))

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
        for symbol in symbols:
            try:
                if multi_symbol:
                    close_series = history[symbol]["Close"].dropna()
                else:
                    close_series = history["Close"].dropna()
                if not close_series.empty:
                    prices[symbol] = float(close_series.iloc[-1])
            except Exception:
                continue
        return prices

    def _fetch_alpaca_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        if not self._alpaca_client or not StockLatestBarRequest:
            return {}
        try:
            request = StockLatestBarRequest(symbol_or_symbols=symbols)
            bars = self._alpaca_client.get_stock_latest_bar(request)
            return {
                symbol: float(bar.close)
                for symbol, bar in bars.items()
                if getattr(bar, "close", None) is not None
            }
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
