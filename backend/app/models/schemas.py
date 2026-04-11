from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Side = Literal["buy", "sell", "short", "cover"]


class Position(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    last_price: float
    market_value: float
    unrealized_pnl: float
    direction: Literal["long", "short"]
    target_weight: float = 0.0


class Trade(BaseModel):
    timestamp: datetime
    symbol: str
    side: Side
    quantity: float
    price: float
    notional: float
    rationale: str
    explanation: str = ""


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float
    cash: float
    gross_exposure: float
    net_exposure: float
    spy_price: float = 0.0


class PortfolioSnapshot(BaseModel):
    timestamp: datetime
    cash: float
    equity: float
    gross_exposure: float
    net_exposure: float
    long_exposure: float
    short_exposure: float
    holdings_count: int


class Signal(BaseModel):
    symbol: str
    score: float
    price: float
    news_sentiment: float
    momentum_20d: float
    reversal_5d: float
    volatility_20d: float
    avg_dollar_volume_20d: float
    target_weight: float = 0.0
    action: Literal["long", "short", "flat"]
    rationale: str


class EngineState(BaseModel):
    initialized_at: datetime
    updated_at: datetime
    cash: float
    positions: dict[str, dict]
    trades: list[Trade] = Field(default_factory=list)
    equity_curve: list[EquityPoint] = Field(default_factory=list)
    last_signals: list[Signal] = Field(default_factory=list)
