import pytest

from app.models.schemas import Signal
from app.services.portfolio import PortfolioService


def test_portfolio_rebalance_creates_trade_and_position(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("app.config.settings.state_file_name", "state.json")
    service = PortfolioService()

    snapshot = service.rebalance(
        [
            Signal(
                symbol="AAPL",
                score=1.0,
                price=100.0,
                news_sentiment=0.2,
                momentum_20d=0.1,
                reversal_5d=0.0,
                volatility_20d=0.2,
                avg_dollar_volume_20d=100_000_000,
                target_weight=0.1,
                action="long",
                rationale="test",
            )
        ],
        {"AAPL": 100.0},
    )

    assert snapshot.equity == 1_000_000.0
    assert snapshot.holdings_count == 1
    trades = service.get_trades()
    assert len(trades) == 1
    assert trades[0].symbol == "AAPL"
    assert trades[0].explanation


def test_closed_positions_uses_trade_prices(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("app.config.settings.state_file_name", "state.json")
    service = PortfolioService()

    service.rebalance(
        [
            Signal(
                symbol="AMD",
                score=1.0,
                price=350.0,
                news_sentiment=0.0,
                momentum_20d=0.0,
                reversal_5d=0.0,
                volatility_20d=0.2,
                avg_dollar_volume_20d=100_000_000,
                target_weight=0.035,
                action="long",
                rationale="test",
            )
        ],
        {"AMD": 350.0},
    )
    service.rebalance([], {"AMD": 305.0})

    closed = service.get_closed_positions()
    assert len(closed) == 1
    assert closed[0].average_entry_price == 350.0
    assert closed[0].average_exit_price == 305.0
    assert closed[0].realized_return_pct == pytest.approx(-12.857142857142858)
