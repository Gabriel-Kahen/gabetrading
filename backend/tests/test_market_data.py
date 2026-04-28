import pandas as pd

from app.services.market_data import MarketDataService


def test_extract_latest_prices_skips_stale_symbol_bar(monkeypatch):
    monkeypatch.setattr("app.config.settings.intraday_interval", "15m")
    service = MarketDataService()
    index = pd.to_datetime(
        [
            "2026-04-23 20:00:00+00:00",
            "2026-04-24 16:00:00+00:00",
        ]
    )
    history = pd.concat(
        {
            "AMD": pd.DataFrame({"Close": [305.33, None]}, index=index),
            "MSFT": pd.DataFrame({"Close": [420.0, 426.0]}, index=index),
        },
        axis=1,
    )

    prices = service._extract_latest_prices(["AMD", "MSFT"], history)

    assert prices == {"MSFT": 426.0}


def test_extract_latest_prices_accepts_recent_symbol_bar(monkeypatch):
    monkeypatch.setattr("app.config.settings.intraday_interval", "15m")
    service = MarketDataService()
    index = pd.to_datetime(
        [
            "2026-04-24 15:45:00+00:00",
            "2026-04-24 16:00:00+00:00",
        ]
    )
    history = pd.concat(
        {
            "AMD": pd.DataFrame({"Close": [350.76, None]}, index=index),
            "MSFT": pd.DataFrame({"Close": [425.0, 426.0]}, index=index),
        },
        axis=1,
    )

    prices = service._extract_latest_prices(["AMD", "MSFT"], history)

    assert prices == {"AMD": 350.76, "MSFT": 426.0}


def test_fetch_snapshot_does_not_execute_from_daily_fallback(monkeypatch):
    service = MarketDataService()
    daily_history = pd.concat(
        {
            "AMD": pd.DataFrame({"Close": [305.33]}, index=pd.to_datetime(["2026-04-23"])),
        },
        axis=1,
    )
    empty_intraday = pd.DataFrame()

    monkeypatch.setattr(service, "_daily_history", lambda symbols: daily_history)
    monkeypatch.setattr(
        "app.services.market_data._download_prices",
        lambda **kwargs: empty_intraday,
    )

    snapshot = service.fetch_snapshot(["AMD"])

    assert snapshot.prices == {}
    assert snapshot.history is daily_history
    assert snapshot.intraday_history is empty_intraday


def test_extract_latest_prices_rejects_non_positive_prices(monkeypatch):
    monkeypatch.setattr("app.config.settings.intraday_interval", "15m")
    service = MarketDataService()
    index = pd.to_datetime(["2026-04-24 16:00:00+00:00"])
    history = pd.concat(
        {
            "AMD": pd.DataFrame({"Close": [0.0]}, index=index),
            "MSFT": pd.DataFrame({"Close": [-1.0]}, index=index),
            "NVDA": pd.DataFrame({"Close": [210.0]}, index=index),
        },
        axis=1,
    )

    prices = service._extract_latest_prices(["AMD", "MSFT", "NVDA"], history)

    assert prices == {"NVDA": 210.0}


def test_alpaca_prices_skip_stale_and_invalid_bars(monkeypatch):
    monkeypatch.setattr("app.config.settings.intraday_interval", "15m")
    service = MarketDataService()

    class FakeBar:
        def __init__(self, close, timestamp):
            self.close = close
            self.timestamp = timestamp

    class FakeClient:
        def get_stock_latest_bar(self, request):
            return {
                "AMD": FakeBar(350.0, pd.Timestamp("2026-04-24 16:00:00+00:00")),
                "MSFT": FakeBar(0.0, pd.Timestamp("2026-04-24 16:00:00+00:00")),
                "NVDA": FakeBar(210.0, pd.Timestamp("2026-04-23 16:00:00+00:00")),
            }

    service._alpaca_client = FakeClient()
    monkeypatch.setattr("app.services.market_data.StockLatestBarRequest", lambda symbol_or_symbols: object())

    prices = service._fetch_alpaca_latest_prices(
        ["AMD", "MSFT", "NVDA"],
        pd.Timestamp("2026-04-24 16:00:00+00:00"),
    )

    assert prices == {"AMD": 350.0}
