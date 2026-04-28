from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from urllib.parse import quote_plus

import feedparser
import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.config import settings


COMPANY_NAMES = {
    "A": "Agilent Technologies",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "Nvidia",
    "AMZN": "Amazon",
    "META": "Meta Platforms",
    "GOOGL": "Alphabet",
    "GOOG": "Alphabet",
    "BRK-B": "Berkshire Hathaway",
    "LLY": "Eli Lilly",
    "AVGO": "Broadcom",
    "JPM": "JPMorgan Chase",
    "XOM": "Exxon Mobil",
    "UNH": "UnitedHealth",
    "V": "Visa",
    "MA": "Mastercard",
    "COST": "Costco",
    "PG": "Procter Gamble",
    "JNJ": "Johnson Johnson",
    "HD": "Home Depot",
    "MRK": "Merck",
    "ABBV": "AbbVie",
    "ORCL": "Oracle",
    "BAC": "Bank of America",
    "CVX": "Chevron",
    "KO": "Coca-Cola",
    "PEP": "PepsiCo",
    "ADBE": "Adobe",
    "WMT": "Walmart",
    "NFLX": "Netflix",
    "AMD": "Advanced Micro Devices",
    "TMO": "Thermo Fisher",
    "MCD": "McDonald's",
    "CSCO": "Cisco",
    "CRM": "Salesforce",
    "ACN": "Accenture",
    "ABT": "Abbott Laboratories",
    "DHR": "Danaher",
    "LIN": "Linde",
    "QCOM": "Qualcomm",
    "TXN": "Texas Instruments",
    "INTU": "Intuit",
    "AMGN": "Amgen",
    "PM": "Philip Morris",
    "IBM": "IBM",
    "CAT": "Caterpillar",
    "GE": "General Electric",
    "NOW": "ServiceNow",
    "DIS": "Disney",
    "SPGI": "S&P Global",
    "VZ": "Verizon",
}


class NewsService:
    def __init__(self) -> None:
        self._analyzer = SentimentIntensityAnalyzer()
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "live-paper-trading-backend/0.1"})
        self._cached_scores: dict[str, float] = {}
        self._cache_expires_at: datetime | None = None

    def score_news(self, symbols: list[str]) -> dict[str, float]:
        now = datetime.now(timezone.utc)
        if self._cache_expires_at and now < self._cache_expires_at:
            return {symbol: self._cached_scores.get(symbol, 0.0) for symbol in symbols}

        scores = defaultdict(list)
        for symbol in symbols:
            entries = self._fetch_symbol_news(symbol)
            for entry in entries:
                headline = f"{entry.get('title', '')} {entry.get('summary', '')}".strip()
                if not headline:
                    continue
                compound = self._analyzer.polarity_scores(headline)["compound"]
                scores[symbol].append(compound)

        market_bias = self._market_wide_bias()
        aggregated: dict[str, float] = {}
        for symbol in symbols:
            values = scores.get(symbol, [])
            base = sum(values) / len(values) if values else 0.0
            aggregated[symbol] = max(min(base + market_bias * 0.15, 1.0), -1.0)

        self._cached_scores = aggregated
        self._cache_expires_at = now + timedelta(seconds=settings.news_refresh_seconds)
        return aggregated

    def _fetch_symbol_news(self, symbol: str) -> list[dict]:
        url = f"https://news.google.com/rss/search?q={quote_plus(self._symbol_news_query(symbol))}&hl=en-US&gl=US&ceid=US:en"
        try:
            parsed = feedparser.parse(self._session.get(url, timeout=10).content)
        except Exception:
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        fresh_entries = []
        for entry in parsed.entries[:8]:
            published = self._entry_published_at(entry)
            if published and published >= cutoff and self._entry_matches_symbol(symbol, entry):
                fresh_entries.append(entry)
        return fresh_entries

    def _market_wide_bias(self) -> float:
        query = "stock market OR business OR economy"
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
        try:
            parsed = feedparser.parse(self._session.get(url, timeout=10).content)
        except Exception:
            return 0.0
        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        sentiments = []
        for entry in parsed.entries[:15]:
            published = self._entry_published_at(entry)
            if not published or published < cutoff:
                continue
            headline = f"{entry.get('title', '')} {entry.get('summary', '')}".strip()
            if headline:
                sentiments.append(self._analyzer.polarity_scores(headline)["compound"])
        return sum(sentiments) / len(sentiments) if sentiments else 0.0

    def _symbol_news_query(self, symbol: str) -> str:
        company_name = COMPANY_NAMES.get(symbol.upper())
        if company_name:
            return f'"{company_name}" {symbol} stock'
        return f"{symbol} stock"

    def _entry_matches_symbol(self, symbol: str, entry: dict) -> bool:
        company_name = COMPANY_NAMES.get(symbol.upper())
        if not company_name:
            return True
        text = f"{entry.get('title', '')} {entry.get('summary', '')}".casefold()
        symbol_token = symbol.replace("-", " ").casefold()
        if len(symbol_token) > 1 and re.search(rf"(?<![a-z0-9]){re.escape(symbol_token)}(?![a-z0-9])", text):
            return True
        for token in company_name.casefold().replace("&", " ").split():
            if len(token) >= 4 and token in text:
                return True
        return False

    @staticmethod
    def _entry_published_at(entry: dict) -> datetime | None:
        published = entry.get("published") or entry.get("updated")
        if not published:
            return None
        try:
            parsed = parsedate_to_datetime(published)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None
