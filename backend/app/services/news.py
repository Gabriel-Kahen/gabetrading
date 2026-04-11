from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser
import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.config import settings


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
        url = f"https://news.google.com/rss/search?q={quote_plus(symbol + ' stock')}&hl=en-US&gl=US&ceid=US:en"
        try:
            parsed = feedparser.parse(self._session.get(url, timeout=10).content)
        except Exception:
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        fresh_entries = []
        for entry in parsed.entries[:8]:
            published = self._entry_published_at(entry)
            if published and published >= cutoff:
                fresh_entries.append(entry)
        return fresh_entries

    def _market_wide_bias(self) -> float:
        url = "https://feeds.reuters.com/reuters/businessNews"
        try:
            parsed = feedparser.parse(self._session.get(url, timeout=10).content)
        except Exception:
            return 0.0
        sentiments = []
        for entry in parsed.entries[:15]:
            headline = f"{entry.get('title', '')} {entry.get('summary', '')}".strip()
            if headline:
                sentiments.append(self._analyzer.polarity_scores(headline)["compound"])
        return sum(sentiments) / len(sentiments) if sentiments else 0.0

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
