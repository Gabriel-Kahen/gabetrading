from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Query

from app.services.trader import TradingOrchestrator


def build_router(orchestrator: TradingOrchestrator) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/portfolio")
    def get_portfolio():
        return orchestrator.portfolio.get_snapshot()

    @router.get("/holdings")
    def get_holdings():
        return orchestrator.portfolio.get_positions()

    @router.get("/trades")
    def get_trades(limit: int | None = Query(default=None, ge=1, le=1000)):
        return orchestrator.portfolio.get_trades(limit=limit)

    @router.get("/closed-positions")
    def get_closed_positions():
        return orchestrator.portfolio.get_closed_positions()

    @router.get("/closed-positions/page")
    def get_closed_positions_page(
        sort: Literal["gainCash", "lossCash", "gainPercent", "lossPercent"] = "gainPercent",
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=10, ge=1, le=100),
    ):
        items, total = orchestrator.portfolio.get_closed_positions_page(sort, page, page_size)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @router.get("/performance")
    def get_performance(
        max_points: int | None = Query(default=None, ge=100, le=5000),
        range_name: Literal["1D", "1W", "1M", "3M", "ALL"] | None = Query(default=None, alias="range"),
    ):
        return orchestrator.portfolio.get_equity_curve(max_points=max_points, range_name=range_name)

    @router.get("/signals")
    def get_signals():
        return orchestrator.portfolio.get_last_signals()

    @router.post("/cycle/run")
    async def run_cycle():
        portfolio, signals = await asyncio.to_thread(orchestrator.run_cycle)
        return {
            "portfolio": portfolio,
            "signals": signals[:25],
        }

    return router
