from __future__ import annotations

import requests

from app.config import settings


class TradeExplanationService:
    def __init__(self) -> None:
        self._enabled = bool(settings.enable_trade_explanations and settings.groq_api_key)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            }
        )

    def explain_trade(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        notional: float,
        rationale: str,
    ) -> str:
        fallback = self._fallback_explanation(symbol=symbol, side=side, rationale=rationale)
        if not self._enabled:
            return fallback

        try:
            response = self._session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                timeout=15,
                json={
                    "model": settings.groq_model,
                    "temperature": 0.2,
                    "max_tokens": 48,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You explain simulated stock trades in exactly one short sentence. "
                                "Use only the supplied trade fields and strategy rationale. "
                                "The only allowed drivers are momentum, reversal, news sentiment, volatility, or signal exit. "
                                "Do not invent catalysts, fundamentals, revenue, earnings, or events. "
                                "Mention the ticker and main driver. Keep it under 24 words."
                            ),
                        },
                        {
                            "role": "user",
                            "content": self._build_prompt(
                                symbol=symbol,
                                side=side,
                                quantity=quantity,
                                price=price,
                                notional=notional,
                                rationale=rationale,
                            ),
                        },
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
            text = (
                payload.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
                .splitlines()[0]
                .strip()
            )
            if not text:
                return fallback
            return text.rstrip(".") + "."
        except Exception:
            return fallback

    def _build_prompt(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        notional: float,
        rationale: str,
    ) -> str:
        return (
            "Explain this simulated stock trade in one quick sentence. "
            "Do not mention prompts, AI, or uncertainty. "
            "Keep it under 24 words.\n\n"
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"Quantity: {quantity:.2f}\n"
            f"Price: {price:.2f}\n"
            f"Notional: {notional:.2f}\n"
            f"Strategy rationale: {rationale}\n\n"
            "Return exactly one sentence."
        )

    def _fallback_explanation(self, *, symbol: str, side: str, rationale: str) -> str:
        if rationale == "signal exited":
            return f"{side.title()} {symbol} because it no longer met the strategy's conviction threshold."
        return f"{side.title()} {symbol} because the strategy score supported this rebalance based on recent price action and news."
