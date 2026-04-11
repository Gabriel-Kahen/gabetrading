from __future__ import annotations

import math

import pandas as pd

from app.config import settings
from app.models.schemas import Signal
from app.services.market_data import symbol_history_frame


class StrategyService:
    def generate_signals(
        self,
        symbols: list[str],
        history: pd.DataFrame,
        intraday_history: pd.DataFrame,
        prices: dict[str, float],
        news_scores: dict[str, float],
    ) -> list[Signal]:
        raw_signals: list[Signal] = []
        for symbol in symbols:
            frame = symbol_history_frame(history, symbol)
            intraday_frame = symbol_history_frame(intraday_history, symbol)
            if frame.empty or intraday_frame.empty or symbol not in prices or len(frame) < 30:
                continue

            close = frame["close"].dropna()
            volume = frame.get("volume", pd.Series(dtype=float)).dropna()
            intraday_close = intraday_frame["close"].dropna()
            intraday_volume = intraday_frame.get("volume", pd.Series(dtype=float)).dropna()
            if len(close) < 25:
                continue
            if len(intraday_close) < 26:
                continue

            momentum_20d = close.iloc[-1] / close.iloc[-21] - 1 if len(close) >= 21 else 0.0
            reversal_5d = -(close.iloc[-1] / close.iloc[-6] - 1) if len(close) >= 6 else 0.0
            daily_returns = close.pct_change().dropna()
            volatility_20d = daily_returns.tail(20).std() * math.sqrt(252) if len(daily_returns) >= 20 else 1.0
            avg_dollar_volume_20d = float((close * volume).tail(20).mean()) if not volume.empty else 0.0
            liquidity_score = min(avg_dollar_volume_20d / 200_000_000, 2.0) - 1.0
            news_sentiment = news_scores.get(symbol, 0.0)
            intraday_momentum = intraday_close.iloc[-1] / intraday_close.iloc[-14] - 1 if len(intraday_close) >= 14 else 0.0
            intraday_reversal = -(intraday_close.iloc[-1] / intraday_close.iloc[-5] - 1) if len(intraday_close) >= 5 else 0.0
            intraday_returns = intraday_close.pct_change().dropna()
            intraday_volatility = (
                intraday_returns.tail(26).std() * math.sqrt(26 * 252) if len(intraday_returns) >= 26 else volatility_20d
            )
            intraday_dollar_volume = float((intraday_close * intraday_volume).tail(26).mean()) if not intraday_volume.empty else 0.0
            intraday_liquidity = min(intraday_dollar_volume / 30_000_000, 2.0) - 1.0

            score = (
                momentum_20d * 1.7
                + reversal_5d * 0.7
                + intraday_momentum * 1.1
                + intraday_reversal * 0.45
                + news_sentiment * 0.9
                + liquidity_score * 0.25
                + intraday_liquidity * 0.15
                - volatility_20d * 0.55
                - intraday_volatility * 0.2
            )

            rationale = (
                f"mom={momentum_20d:.2%}, rev={reversal_5d:.2%}, "
                f"imom={intraday_momentum:.2%}, irev={intraday_reversal:.2%}, "
                f"news={news_sentiment:.2f}, vol={volatility_20d:.2%}"
            )
            raw_signals.append(
                Signal(
                    symbol=symbol,
                    score=score,
                    price=prices[symbol],
                    news_sentiment=news_sentiment,
                    momentum_20d=momentum_20d,
                    reversal_5d=reversal_5d,
                    volatility_20d=volatility_20d,
                    avg_dollar_volume_20d=avg_dollar_volume_20d,
                    action="flat",
                    rationale=rationale,
                )
            )

        ranked = sorted(raw_signals, key=lambda item: item.score, reverse=True)
        longs = [s for s in ranked if s.score >= settings.long_score_threshold][: settings.max_longs]
        shorts = [s for s in reversed(ranked) if s.score <= settings.short_score_threshold][: settings.max_shorts]
        self._assign_target_weights(longs, is_short=False)
        self._assign_target_weights(shorts, is_short=True)

        selected = {s.symbol: s for s in longs + shorts}
        final_signals = []
        for signal in ranked:
            chosen = selected.get(signal.symbol)
            final_signals.append(chosen or signal)
        return final_signals

    def _assign_target_weights(self, signals: list[Signal], is_short: bool) -> None:
        if not signals:
            return
        inverse_vols = [1 / max(signal.volatility_20d, 0.15) for signal in signals]
        total = sum(inverse_vols)
        gross_side_limit = settings.gross_exposure_limit * (0.42 if is_short else 0.58)
        sign = -1.0 if is_short else 1.0
        for signal, inverse_vol in zip(signals, inverse_vols):
            raw_weight = gross_side_limit * inverse_vol / total
            signal.target_weight = sign * min(raw_weight, settings.max_position_weight)
            signal.action = "short" if is_short else "long"
