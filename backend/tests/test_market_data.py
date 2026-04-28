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
