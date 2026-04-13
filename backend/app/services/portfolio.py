from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from app.config import settings
from app.models.schemas import ClosedPosition, EngineState, EquityPoint, PortfolioSnapshot, Position, Signal, Trade
from app.services.explanations import TradeExplanationService


class PortfolioService:
    def __init__(self, explanation_service: TradeExplanationService | None = None) -> None:
        self._lock = Lock()
        self._explanation_service = explanation_service or TradeExplanationService()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self._state = self._load_or_initialize(settings.state_file)

    def get_snapshot(self, prices: dict[str, float] | None = None) -> PortfolioSnapshot:
        with self._lock:
            return self._build_snapshot(prices or {})

    def get_positions(self, prices: dict[str, float] | None = None) -> list[Position]:
        with self._lock:
            return self._build_positions(prices or {})

    def get_trades(self) -> list[Trade]:
        with self._lock:
            return list(reversed(self._state.trades))

    def get_closed_positions(self) -> list[ClosedPosition]:
        with self._lock:
            return self._build_closed_positions()

    def get_equity_curve(self) -> list[EquityPoint]:
        with self._lock:
            return self._state.equity_curve

    def get_last_signals(self) -> list[Signal]:
        with self._lock:
            return self._state.last_signals

    def rebalance(self, signals: list[Signal], prices: dict[str, float]) -> PortfolioSnapshot:
        with self._lock:
            equity = self._equity(prices)
            target_weights = {signal.symbol: signal.target_weight for signal in signals if signal.target_weight != 0.0}

            existing_symbols = set(self._state.positions)
            symbols_to_flatten = existing_symbols - set(target_weights)
            for symbol in symbols_to_flatten:
                price = prices.get(symbol)
                if price:
                    self._trade_to_target_value(symbol, 0.0, price, rationale="signal exited")

            for signal in signals:
                if signal.target_weight == 0.0:
                    continue
                price = prices.get(signal.symbol)
                if not price:
                    continue
                target_value = equity * signal.target_weight
                if self._should_skip_rebalance(signal.symbol, target_value, price, equity):
                    continue
                self._trade_to_target_value(signal.symbol, target_value, price, rationale=signal.rationale)

            for symbol, target_weight in target_weights.items():
                if symbol in self._state.positions:
                    self._state.positions[symbol]["target_weight"] = target_weight

            self._mark_prices(prices)
            self._state.last_signals = signals[:50]
            self._record_equity_point(prices)
            self._state.updated_at = datetime.now(timezone.utc)
            self._persist(settings.state_file)
            return self._build_snapshot(prices)

    def _should_skip_rebalance(self, symbol: str, target_value: float, price: float, equity: float) -> bool:
        current = self._state.positions.get(symbol)
        if not current:
            return False

        current_value = float(current["quantity"]) * price
        value_change = abs(target_value - current_value)
        weight_change = value_change / max(equity, 1.0)
        if value_change < settings.min_rebalance_notional and weight_change < settings.min_rebalance_weight_change:
            return True
        return False

    def _trade_to_target_value(self, symbol: str, target_value: float, price: float, rationale: str) -> None:
        current = self._state.positions.get(symbol, {"quantity": 0.0, "average_price": price})
        current_quantity = float(current["quantity"])
        target_quantity = target_value / price
        delta_quantity = target_quantity - current_quantity
        if abs(delta_quantity) < 0.01:
            return

        if delta_quantity > 0:
            side = "buy" if current_quantity >= 0 else "cover"
            cash_delta = -delta_quantity * price
        else:
            side = "sell" if current_quantity > 0 else "short"
            cash_delta = -delta_quantity * price

        new_quantity = current_quantity + delta_quantity
        if abs(new_quantity) < 0.01:
            self._state.positions.pop(symbol, None)
        else:
            average_price = self._updated_average_price(current_quantity, float(current["average_price"]), delta_quantity, price)
            self._state.positions[symbol] = {
                "quantity": new_quantity,
                "average_price": average_price,
                "last_price": price,
                "target_weight": 0.0,
            }

        self._state.cash += cash_delta
        self._state.trades.append(
            Trade(
                timestamp=datetime.now(timezone.utc),
                symbol=symbol,
                side=side,
                quantity=abs(delta_quantity),
                price=price,
                notional=abs(delta_quantity * price),
                rationale=rationale,
                explanation=self._explanation_service.explain_trade(
                    symbol=symbol,
                    side=side,
                    quantity=abs(delta_quantity),
                    price=price,
                    notional=abs(delta_quantity * price),
                    rationale=rationale,
                ),
            )
        )

    def _updated_average_price(
        self,
        current_quantity: float,
        current_average_price: float,
        delta_quantity: float,
        execution_price: float,
    ) -> float:
        new_quantity = current_quantity + delta_quantity
        if abs(new_quantity) < 0.01:
            return execution_price
        if current_quantity == 0 or (current_quantity > 0) != (new_quantity > 0):
            return execution_price
        if (current_quantity > 0) == (delta_quantity > 0):
            total_cost = current_quantity * current_average_price + delta_quantity * execution_price
            return abs(total_cost / new_quantity)
        return current_average_price

    def _mark_prices(self, prices: dict[str, float]) -> None:
        for symbol, position in list(self._state.positions.items()):
            if symbol in prices:
                position["last_price"] = prices[symbol]

    def _equity(self, prices: dict[str, float]) -> float:
        equity = self._state.cash
        for symbol, position in self._state.positions.items():
            price = prices.get(symbol, position.get("last_price", position["average_price"]))
            equity += position["quantity"] * price
        return equity

    def _build_snapshot(self, prices: dict[str, float]) -> PortfolioSnapshot:
        positions = self._build_positions(prices)
        long_exposure = sum(max(position.market_value, 0.0) for position in positions)
        short_exposure = sum(-min(position.market_value, 0.0) for position in positions)
        equity = self._equity(prices)
        gross = long_exposure + short_exposure
        return PortfolioSnapshot(
            timestamp=datetime.now(timezone.utc),
            cash=self._state.cash,
            equity=equity,
            gross_exposure=gross,
            net_exposure=long_exposure - short_exposure,
            long_exposure=long_exposure,
            short_exposure=short_exposure,
            holdings_count=len(positions),
        )

    def _build_positions(self, prices: dict[str, float]) -> list[Position]:
        positions = []
        for symbol, payload in self._state.positions.items():
            last_price = prices.get(symbol, payload.get("last_price", payload["average_price"]))
            quantity = float(payload["quantity"])
            market_value = quantity * last_price
            direction = "long" if quantity >= 0 else "short"
            if quantity >= 0:
                pnl = (last_price - payload["average_price"]) * quantity
            else:
                pnl = (payload["average_price"] - last_price) * abs(quantity)
            positions.append(
                Position(
                    symbol=symbol,
                    quantity=quantity,
                    average_price=float(payload["average_price"]),
                    last_price=float(last_price),
                    market_value=float(market_value),
                    unrealized_pnl=float(pnl),
                    direction=direction,
                    target_weight=float(payload.get("target_weight", 0.0)),
                )
            )
        return sorted(positions, key=lambda item: abs(item.market_value), reverse=True)

    def _record_equity_point(self, prices: dict[str, float]) -> None:
        snapshot = self._build_snapshot(prices)
        self._state.equity_curve.append(
            EquityPoint(
                timestamp=datetime.now(timezone.utc),
                equity=snapshot.equity,
                cash=snapshot.cash,
                gross_exposure=snapshot.gross_exposure,
                net_exposure=snapshot.net_exposure,
                spy_price=prices.get("SPY", 0.0),
            )
        )
        self._state.equity_curve = self._state.equity_curve[-1000:]
        self._state.trades = self._state.trades[-5000:]

    def _build_closed_positions(self) -> list[ClosedPosition]:
        lots_by_symbol: dict[str, list[dict]] = {}
        lifecycle_by_symbol: dict[str, dict] = {}
        closed_positions: list[ClosedPosition] = []

        for trade in self._state.trades:
            if trade.side in {"buy", "cover"}:
                incoming_direction = "long"
                incoming_quantity = float(trade.quantity)
            else:
                incoming_direction = "short"
                incoming_quantity = float(trade.quantity)

            lots = lots_by_symbol.setdefault(trade.symbol, [])
            lifecycle = lifecycle_by_symbol.get(trade.symbol)

            if not lots:
                lifecycle = self._start_lifecycle(trade, incoming_direction)
                lifecycle_by_symbol[trade.symbol] = lifecycle

            remaining_quantity = incoming_quantity
            while remaining_quantity > 0 and lots and lots[0]["direction"] != incoming_direction:
                open_lot = lots[0]
                matched_quantity = min(remaining_quantity, open_lot["quantity"])

                if open_lot["direction"] == "long":
                    realized_pnl = (trade.price - open_lot["price"]) * matched_quantity
                else:
                    realized_pnl = (open_lot["price"] - trade.price) * matched_quantity

                if lifecycle is None:
                    lifecycle = self._start_lifecycle_from_lot(open_lot)
                    lifecycle_by_symbol[trade.symbol] = lifecycle

                lifecycle["closed_quantity"] += matched_quantity
                lifecycle["entry_notional"] += open_lot["price"] * matched_quantity
                lifecycle["exit_notional"] += trade.price * matched_quantity
                lifecycle["realized_pnl"] += realized_pnl
                lifecycle["closed_at"] = trade.timestamp

                open_lot["quantity"] -= matched_quantity
                remaining_quantity -= matched_quantity

                if open_lot["quantity"] <= 1e-9:
                    lots.pop(0)

            if lifecycle is not None and not lots and lifecycle["closed_quantity"] > 0:
                closed_positions.append(
                    ClosedPosition(
                        symbol=trade.symbol,
                        direction=lifecycle["direction"],
                        opened_at=lifecycle["opened_at"],
                        closed_at=lifecycle["closed_at"],
                        quantity=lifecycle["closed_quantity"],
                        average_entry_price=lifecycle["entry_notional"] / lifecycle["closed_quantity"],
                        average_exit_price=lifecycle["exit_notional"] / lifecycle["closed_quantity"],
                        realized_pnl=lifecycle["realized_pnl"],
                        realized_return_pct=(lifecycle["realized_pnl"] / lifecycle["entry_notional"]) * 100
                        if lifecycle["entry_notional"] > 0
                        else 0.0,
                    )
                )
                lifecycle = None
                lifecycle_by_symbol.pop(trade.symbol, None)

            if remaining_quantity > 0:
                if not lots and lifecycle is None:
                    lifecycle = self._start_lifecycle(trade, incoming_direction)
                    lifecycle_by_symbol[trade.symbol] = lifecycle
                lots.append(
                    {
                        "quantity": remaining_quantity,
                        "price": float(trade.price),
                        "timestamp": trade.timestamp,
                        "direction": incoming_direction,
                    }
                )

        return list(reversed(closed_positions))

    def _start_lifecycle(self, trade: Trade, direction: str) -> dict:
        return {
            "direction": direction,
            "opened_at": trade.timestamp,
            "closed_at": trade.timestamp,
            "closed_quantity": 0.0,
            "entry_notional": 0.0,
            "exit_notional": 0.0,
            "realized_pnl": 0.0,
        }

    def _start_lifecycle_from_lot(self, lot: dict) -> dict:
        return {
            "direction": lot["direction"],
            "opened_at": lot["timestamp"],
            "closed_at": lot["timestamp"],
            "closed_quantity": 0.0,
            "entry_notional": 0.0,
            "exit_notional": 0.0,
            "realized_pnl": 0.0,
        }

    def _load_or_initialize(self, path: Path) -> EngineState:
        if path.exists():
            payload = json.loads(path.read_text())
            return EngineState.model_validate(payload)
        now = datetime.now(timezone.utc)
        state = EngineState(
            initialized_at=now,
            updated_at=now,
            cash=settings.starting_capital,
            positions={},
            trades=[],
            equity_curve=[],
            last_signals=[],
        )
        self._persist(path, state)
        return state

    def _persist(self, path: Path, state: EngineState | None = None) -> None:
        target_state = state or self._state
        path.write_text(target_state.model_dump_json(indent=2))
