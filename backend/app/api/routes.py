from __future__ import annotations

import asyncio

from fastapi import APIRouter

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
    def get_trades():
        return orchestrator.portfolio.get_trades()

    @router.get("/closed-positions")
    def get_closed_positions():
        return orchestrator.portfolio.get_closed_positions()

    @router.get("/performance")
    def get_performance():
        return orchestrator.portfolio.get_equity_curve()

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
