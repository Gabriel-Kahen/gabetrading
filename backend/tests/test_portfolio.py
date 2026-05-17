import json

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

    assert snapshot.equity == 100_000.0
    assert snapshot.holdings_count == 1
    trades = service.get_trades()
    assert len(trades) == 1
    assert trades[0].symbol == "AAPL"
    assert trades[0].explanation
    assert (tmp_path / "state.sqlite3").exists()


def test_portfolio_reloads_from_sqlite(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("app.config.settings.state_file_name", "state.json")
    monkeypatch.setattr("app.config.settings.database_file_name", "state.sqlite3")
    service = PortfolioService()

    service.rebalance(
        [
            Signal(
                symbol="MSFT",
                score=1.0,
                price=200.0,
                news_sentiment=0.0,
                momentum_20d=0.0,
                reversal_5d=0.0,
                volatility_20d=0.2,
                avg_dollar_volume_20d=100_000_000,
                target_weight=0.2,
                action="long",
                rationale="test",
            )
        ],
        {"MSFT": 200.0},
    )

    reloaded = PortfolioService()

    assert reloaded.get_snapshot({"MSFT": 210.0}).holdings_count == 1
    assert reloaded.get_positions({"MSFT": 210.0})[0].symbol == "MSFT"
    assert len(reloaded.get_trades()) == 1
    assert len(reloaded.get_equity_curve()) == 1


def test_portfolio_migrates_legacy_json_state(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("app.config.settings.state_file_name", "state.json")
    monkeypatch.setattr("app.config.settings.database_file_name", "state.sqlite3")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "initialized_at": "2026-05-01T13:30:00+00:00",
                "updated_at": "2026-05-01T13:35:00+00:00",
                "cash": 900_000.0,
                "positions": {
                    "AAPL": {
                        "quantity": 10.0,
                        "average_price": 100.0,
                        "last_price": 110.0,
                        "target_weight": 0.1,
                    }
                },
                "trades": [
                    {
                        "timestamp": "2026-05-01T13:31:00+00:00",
                        "symbol": "AAPL",
                        "side": "buy",
                        "quantity": 10.0,
                        "price": 100.0,
                        "notional": 1000.0,
                        "rationale": "legacy",
                        "explanation": "legacy import",
                    }
                ],
                "equity_curve": [
                    {
                        "timestamp": "2026-05-01T13:35:00+00:00",
                        "equity": 901_100.0,
                        "cash": 900_000.0,
                        "gross_exposure": 1_100.0,
                        "net_exposure": 1_100.0,
                        "spy_price": 500.0,
                    }
                ],
                "last_signals": [],
            }
        )
    )

    service = PortfolioService()
    reloaded = PortfolioService()

    expected_scale = 100_000.0 / 901_100.0

    assert service.get_trades()[0].rationale == "legacy"
    assert service.get_trades()[0].quantity == pytest.approx(10.0 * expected_scale)
    assert service.get_trades()[0].notional == pytest.approx(1000.0 * expected_scale)
    assert reloaded.get_positions({"AAPL": 111.0})[0].symbol == "AAPL"
    assert reloaded.get_positions({"AAPL": 111.0})[0].quantity == pytest.approx(10.0 * expected_scale)
    assert reloaded.get_equity_curve()[0].equity == pytest.approx(100_000.0)
    assert reloaded.get_equity_curve()[0].cash == pytest.approx(900_000.0 * expected_scale)


def test_portfolio_migrates_legacy_json_without_equity_curve(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("app.config.settings.state_file_name", "state.json")
    monkeypatch.setattr("app.config.settings.database_file_name", "state.sqlite3")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "initialized_at": "2026-05-01T13:30:00+00:00",
                "updated_at": "2026-05-01T13:35:00+00:00",
                "cash": 1_000_000.0,
                "positions": {},
                "trades": [],
                "equity_curve": [],
                "last_signals": [],
            }
        )
    )

    service = PortfolioService()
    reloaded = PortfolioService()

    assert service.get_snapshot().equity == pytest.approx(100_000.0)
    assert reloaded.get_snapshot().equity == pytest.approx(100_000.0)


def test_empty_sqlite_state_still_imports_legacy_json(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("app.config.settings.state_file_name", "state.json")
    monkeypatch.setattr("app.config.settings.database_file_name", "state.sqlite3")
    PortfolioService()
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "initialized_at": "2026-05-01T13:30:00+00:00",
                "updated_at": "2026-05-01T13:35:00+00:00",
                "cash": 900_000.0,
                "positions": {
                    "AAPL": {
                        "quantity": 10.0,
                        "average_price": 100.0,
                        "last_price": 110.0,
                        "target_weight": 0.1,
                    }
                },
                "trades": [],
                "equity_curve": [],
                "last_signals": [],
            }
        )
    )

    reloaded = PortfolioService()
    expected_scale = 100_000.0 / 901_100.0

    assert reloaded.get_snapshot({"AAPL": 110.0}).equity == pytest.approx(100_000.0)
    assert reloaded.get_positions({"AAPL": 110.0})[0].quantity == pytest.approx(10.0 * expected_scale)


def test_portfolio_prefers_existing_sqlite_over_legacy_json(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("app.config.settings.state_file_name", "state.json")
    monkeypatch.setattr("app.config.settings.database_file_name", "state.sqlite3")
    service = PortfolioService()
    service.rebalance(
        [
            Signal(
                symbol="MSFT",
                score=1.0,
                price=200.0,
                news_sentiment=0.0,
                momentum_20d=0.0,
                reversal_5d=0.0,
                volatility_20d=0.2,
                avg_dollar_volume_20d=100_000_000,
                target_weight=0.2,
                action="long",
                rationale="sqlite state",
            )
        ],
        {"MSFT": 200.0},
    )
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "initialized_at": "2026-05-01T13:30:00+00:00",
                "updated_at": "2026-05-01T13:35:00+00:00",
                "cash": 50_000.0,
                "positions": {},
                "trades": [],
                "equity_curve": [],
                "last_signals": [],
            }
        )
    )

    reloaded = PortfolioService()

    assert reloaded.get_positions({"MSFT": 200.0})[0].symbol == "MSFT"
    assert reloaded.get_trades()[0].rationale == "sqlite state"


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
