from datetime import datetime, timezone

from app.services.news import NewsService


def test_symbol_news_query_uses_company_name_for_ambiguous_ticker():
    query = NewsService()._symbol_news_query("NOW")

    assert "ServiceNow" in query
    assert "NOW" in query


def test_entry_matches_symbol_filters_unrelated_short_ticker_news():
    service = NewsService()

    assert service._entry_matches_symbol(
        "V",
        {"title": "Visa earnings lift card network stocks", "summary": ""},
    )
    assert not service._entry_matches_symbol(
        "V",
        {"title": "Five top stocks to buy right now", "summary": ""},
    )


def test_entry_published_at_normalizes_to_utc():
    parsed = NewsService._entry_published_at({"published": "Tue, 28 Apr 2026 12:00:00 -0400"})

    assert parsed == datetime(2026, 4, 28, 16, 0, tzinfo=timezone.utc)
