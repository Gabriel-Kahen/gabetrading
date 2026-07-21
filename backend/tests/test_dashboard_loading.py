from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from threading import Lock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import build_router
from app.models.schemas import ClosedPosition, EquityPoint
from app.services.portfolio import PortfolioService


def make_service(*, trades=None, equity_curve=None) -> PortfolioService:
    service = object.__new__(PortfolioService)
    service._lock = Lock()
    service._state = SimpleNamespace(
        trades=list(trades or []),
        equity_curve=list(equity_curve or []),
    )
    service._closed_positions_cache_trade_count = -1
    service._closed_positions_cache = []
    return service


def test_recent_trades_are_bounded_and_newest_first():
    service = make_service(trades=range(10))

    assert service.get_trades(limit=3) == [9, 8, 7]
    assert service.get_trades() == list(reversed(range(10)))


def test_equity_curve_downsampling_preserves_first_and_last_points():
    service = make_service(equity_curve=range(10))

    assert service.get_equity_curve(max_points=4) == [0, 3, 6, 9]
    assert service.get_equity_curve() == list(range(10))


def test_equity_curve_filters_range_before_downsampling():
    now = datetime.now(timezone.utc)
    points = [
        EquityPoint(
            timestamp=now - timedelta(days=days_ago),
            equity=100 + days_ago,
            cash=100,
            gross_exposure=0,
            net_exposure=0,
        )
        for days_ago in reversed(range(10))
    ]
    service = make_service(equity_curve=points)

    result = service.get_equity_curve(max_points=100, range_name="1W")

    assert len(result) == 8
    assert result[0].timestamp == now - timedelta(days=7)
    assert result[-1].timestamp == now


def test_closed_positions_page_sorts_before_slicing():
    service = make_service()
    now = datetime.now(timezone.utc)
    service._closed_positions_cache_trade_count = 0
    service._closed_positions_cache = [
        ClosedPosition(
            symbol=symbol,
            direction="long",
            opened_at=now,
            closed_at=now,
            quantity=1,
            average_entry_price=100,
            average_exit_price=100 + pnl,
            realized_pnl=pnl,
            realized_return_pct=pnl,
        )
        for symbol, pnl in [("MID", 2), ("TOP", 8), ("LOW", -5)]
    ]

    page, total = service.get_closed_positions_page("gainPercent", page=1, page_size=2)

    assert total == 3
    assert [position.symbol for position in page] == ["TOP", "MID"]


class FakePortfolio:
    def get_trades(self, limit=None):
        return [{"limit": limit}]

    def get_equity_curve(self, max_points=None, range_name=None):
        return [{"max_points": max_points, "range": range_name}]

    def get_closed_positions_page(self, sort, page, page_size):
        return [], 42


def test_dashboard_routes_forward_bounding_parameters():
    app = FastAPI()
    app.include_router(build_router(SimpleNamespace(portfolio=FakePortfolio())))

    with TestClient(app) as client:
        trades = client.get("/trades?limit=250")
        performance = client.get("/performance?range=1W&max_points=1500")
        closed = client.get("/closed-positions/page?sort=lossCash&page=2&page_size=10")

    assert trades.json() == [{"limit": 250}]
    assert performance.json() == [{"max_points": 1500, "range": "1W"}]
    assert closed.json() == {
        "items": [],
        "total": 42,
        "page": 2,
        "page_size": 10,
    }


def test_dashboard_route_limits_are_validated():
    app = FastAPI()
    app.include_router(build_router(SimpleNamespace(portfolio=FakePortfolio())))

    with TestClient(app) as client:
        assert client.get("/trades?limit=0").status_code == 422
        assert client.get("/trades?limit=1001").status_code == 422
        assert client.get("/performance?max_points=99").status_code == 422
        assert client.get("/performance?max_points=5001").status_code == 422
        assert client.get("/performance?range=1Y").status_code == 422
        assert client.get("/closed-positions/page?page_size=101").status_code == 422
