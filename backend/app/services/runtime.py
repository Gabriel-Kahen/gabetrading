from __future__ import annotations

import asyncio
import datetime
import logging

import requests
from zoneinfo import ZoneInfo

from app.config import settings
from app.services.trader import TradingOrchestrator


logger = logging.getLogger(__name__)


def _is_market_open() -> bool:
    try:
        url = "https://paper-api.alpaca.markets/v2/clock"
        headers = {}
        if settings.alpaca_api_key and settings.alpaca_secret_key:
            headers["APCA-API-KEY-ID"] = settings.alpaca_api_key
            headers["APCA-API-SECRET-KEY"] = settings.alpaca_secret_key
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("is_open", False)
        logger.warning(f"Failed to fetch Alpaca clock, status: {resp.status_code}")
    except Exception as e:
        logger.error(f"Error checking market clock: {e}")
    
    logger.info("Falling back to local time check for market hours.")
    ny_time = datetime.datetime.now(ZoneInfo("America/New_York"))
    if ny_time.weekday() > 4:
        return False
    market_open = datetime.time(9, 30)
    market_close = datetime.time(16, 0)
    return market_open <= ny_time.time() <= market_close


class RuntimeService:
    def __init__(self, orchestrator: TradingOrchestrator) -> None:
        self.orchestrator = orchestrator
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task:
            return
        if settings.auto_run_on_start:
            asyncio.create_task(self._run_cycle_safe())
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            is_open = await asyncio.to_thread(_is_market_open)
            if is_open:
                await self._run_cycle_safe(skip_clock_check=True)
                await asyncio.sleep(settings.trading_interval_seconds)
                continue

            logger.info("Market is currently closed. Waiting for the next RTH poll.")
            await asyncio.sleep(settings.market_closed_poll_seconds)

    async def _run_cycle_safe(self, skip_clock_check: bool = False) -> None:
        try:
            if not skip_clock_check:
                is_open = await asyncio.to_thread(_is_market_open)
                if not is_open:
                    logger.info("Market is currently closed. Skipping trading cycle.")
                    return
            await asyncio.to_thread(self.orchestrator.run_cycle)
        except Exception:
            logger.exception("trading cycle failed")
