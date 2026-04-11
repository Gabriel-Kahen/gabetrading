from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from app.config import settings


FALLBACK_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK-B", "LLY", "AVGO",
    "JPM", "XOM", "UNH", "V", "MA", "COST", "PG", "JNJ", "HD", "MRK",
    "ABBV", "ORCL", "BAC", "CVX", "KO", "PEP", "ADBE", "WMT", "NFLX", "AMD",
    "TMO", "MCD", "CSCO", "CRM", "ACN", "ABT", "DHR", "LIN", "QCOM", "TXN",
    "INTU", "AMGN", "PM", "IBM", "CAT", "GE", "NOW", "DIS", "SPGI", "VZ",
]


_CACHED_SYMBOLS: list[str] = []
_CACHE_EXPIRES_AT: datetime | None = None


def load_sp500_symbols() -> list[str]:
    global _CACHED_SYMBOLS, _CACHE_EXPIRES_AT

    now = datetime.now(timezone.utc)
    if _CACHE_EXPIRES_AT and now < _CACHE_EXPIRES_AT and _CACHED_SYMBOLS:
        return _CACHED_SYMBOLS[: settings.universe_limit]

    try:
        table = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        symbols = table["Symbol"].astype(str).tolist()
    except Exception:
        symbols = FALLBACK_SYMBOLS

    cleaned = []
    for symbol in symbols:
        ticker = symbol.replace(".", "-").strip().upper()
        if ticker and ticker not in cleaned:
            cleaned.append(ticker)

    _CACHED_SYMBOLS = cleaned
    _CACHE_EXPIRES_AT = now + timedelta(seconds=settings.universe_refresh_seconds)
    return _CACHED_SYMBOLS[: settings.universe_limit]
