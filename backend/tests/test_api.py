import threading

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.services.market_data import MarketDataService
from app.services.trader import TradingOrchestrator


def test_health_endpoint(monkeypatch):
    monkeypatch.setattr("app.config.settings.auto_run_on_start", False)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_run_cycle_endpoint_uses_worker_thread(monkeypatch):
    monkeypatch.setattr("app.config.settings.auto_run_on_start", False)
    to_thread_called = False

    def fake_run_cycle():
        return {"cash": 1}, []

    async def fake_to_thread(func, *args, **kwargs):
        nonlocal to_thread_called
        to_thread_called = True
        return func(*args, **kwargs)

    monkeypatch.setattr("app.main.orchestrator.run_cycle", fake_run_cycle)
    monkeypatch.setattr("app.api.routes.asyncio.to_thread", fake_to_thread)
    with TestClient(app) as client:
        response = client.post("/cycle/run")

    assert response.status_code == 200
    assert response.json() == {"portfolio": {"cash": 1}, "signals": []}
    assert to_thread_called


def test_yfinance_downloads_disable_threads(monkeypatch):
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame()

    monkeypatch.setattr("app.services.market_data.yf.download", fake_download)
    service = MarketDataService()
    service._daily_history(["AAPL"])
    service.fetch_snapshot(["AAPL"])

    assert calls
    assert all(call["threads"] is False for call in calls)


def test_run_cycle_is_serialized(monkeypatch):
    orchestrator = TradingOrchestrator()
    entered = threading.Event()
    release = threading.Event()
    call_count = 0

    def slow_fetch_snapshot(symbols):
        nonlocal call_count
        call_count += 1
        entered.set()
        release.wait(timeout=2)
        return type("Snapshot", (), {"history": [], "intraday_history": [], "prices": {}})()

    monkeypatch.setattr(orchestrator.market_data, "fetch_snapshot", slow_fetch_snapshot)
    monkeypatch.setattr(orchestrator.news, "score_news", lambda symbols: {})
    monkeypatch.setattr(orchestrator.strategy, "generate_signals", lambda *args: [])
    monkeypatch.setattr(orchestrator.portfolio, "rebalance", lambda signals, prices: {})

    first = threading.Thread(target=orchestrator.run_cycle)
    first.start()
    assert entered.wait(timeout=2)

    second = threading.Thread(target=orchestrator.run_cycle)
    second.start()
    assert call_count == 1

    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert call_count == 2
