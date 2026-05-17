from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.models.schemas import EngineState


SCHEMA_VERSION = 1


class PortfolioStore:
    def __init__(self, database_path: Path, legacy_state_path: Path) -> None:
        self.database_path = database_path
        self.legacy_state_path = legacy_state_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def load_or_initialize(self) -> EngineState:
        if self._has_state():
            legacy_ready_for_import = (
                self.legacy_state_path.exists()
                and self._is_empty_state()
                and not self._metadata_value("legacy_imported_at")
            )
            if legacy_ready_for_import:
                return self._import_legacy_state()
            return self._load()

        if self.legacy_state_path.exists():
            return self._import_legacy_state()

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
        self.save(state)
        self._set_metadata("initialized_from", "fresh")
        return state

    def _import_legacy_state(self) -> EngineState:
        payload = json.loads(self.legacy_state_path.read_text())
        state = EngineState.model_validate(payload)
        state = _rebase_state_to_starting_equity(state, settings.starting_capital)
        self.save(state)
        self._set_metadata("initialized_from", "legacy_json")
        self._set_metadata("legacy_imported_at", _encode_datetime(datetime.now(timezone.utc)))
        self._set_metadata("legacy_state_path", str(self.legacy_state_path))
        return state

    def save(self, state: EngineState) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO engine_state (id, initialized_at, updated_at, cash)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    initialized_at = excluded.initialized_at,
                    updated_at = excluded.updated_at,
                    cash = excluded.cash
                """,
                (
                    _encode_datetime(state.initialized_at),
                    _encode_datetime(state.updated_at),
                    state.cash,
                ),
            )

            conn.execute("DELETE FROM positions")
            conn.executemany(
                """
                INSERT INTO positions (symbol, quantity, average_price, last_price, target_weight)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        symbol,
                        float(payload["quantity"]),
                        float(payload["average_price"]),
                        float(payload.get("last_price", payload["average_price"])),
                        float(payload.get("target_weight", 0.0)),
                    )
                    for symbol, payload in state.positions.items()
                ],
            )

            conn.execute("DELETE FROM trades")
            conn.executemany(
                """
                INSERT INTO trades (
                    timestamp, symbol, side, quantity, price, notional, rationale, explanation
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        _encode_datetime(trade.timestamp),
                        trade.symbol,
                        trade.side,
                        trade.quantity,
                        trade.price,
                        trade.notional,
                        trade.rationale,
                        trade.explanation,
                    )
                    for trade in state.trades
                ],
            )

            conn.execute("DELETE FROM equity_points")
            conn.executemany(
                """
                INSERT INTO equity_points (timestamp, equity, cash, gross_exposure, net_exposure, spy_price)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        _encode_datetime(point.timestamp),
                        point.equity,
                        point.cash,
                        point.gross_exposure,
                        point.net_exposure,
                        point.spy_price,
                    )
                    for point in state.equity_curve
                ],
            )

            conn.execute("DELETE FROM signals")
            conn.executemany(
                """
                INSERT INTO signals (
                    rank, symbol, score, price, news_sentiment, momentum_20d, reversal_5d,
                    volatility_20d, avg_dollar_volume_20d, target_weight, action, rationale
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        rank,
                        signal.symbol,
                        signal.score,
                        signal.price,
                        signal.news_sentiment,
                        signal.momentum_20d,
                        signal.reversal_5d,
                        signal.volatility_20d,
                        signal.avg_dollar_volume_20d,
                        signal.target_weight,
                        signal.action,
                        signal.rationale,
                    )
                    for rank, signal in enumerate(state.last_signals)
                ],
            )

    def _load(self) -> EngineState:
        with self._connect() as conn:
            meta = conn.execute("SELECT initialized_at, updated_at, cash FROM engine_state WHERE id = 1").fetchone()
            positions = {
                row["symbol"]: {
                    "quantity": row["quantity"],
                    "average_price": row["average_price"],
                    "last_price": row["last_price"],
                    "target_weight": row["target_weight"],
                }
                for row in conn.execute(
                    "SELECT symbol, quantity, average_price, last_price, target_weight FROM positions ORDER BY symbol"
                )
            }
            trades = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT timestamp, symbol, side, quantity, price, notional, rationale, explanation
                    FROM trades
                    ORDER BY id
                    """
                )
            ]
            equity_curve = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT timestamp, equity, cash, gross_exposure, net_exposure, spy_price
                    FROM equity_points
                    ORDER BY id
                    """
                )
            ]
            last_signals = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT symbol, score, price, news_sentiment, momentum_20d, reversal_5d,
                           volatility_20d, avg_dollar_volume_20d, target_weight, action, rationale
                    FROM signals
                    ORDER BY rank
                    """
                )
            ]

        return EngineState.model_validate(
            {
                "initialized_at": meta["initialized_at"],
                "updated_at": meta["updated_at"],
                "cash": meta["cash"],
                "positions": positions,
                "trades": trades,
                "equity_curve": equity_curve,
                "last_signals": last_signals,
            }
        )

    def _has_state(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM engine_state WHERE id = 1").fetchone()
        return row is not None

    def _is_empty_state(self) -> bool:
        with self._connect() as conn:
            positions = conn.execute("SELECT 1 FROM positions LIMIT 1").fetchone()
            trades = conn.execute("SELECT 1 FROM trades LIMIT 1").fetchone()
            equity_points = conn.execute("SELECT 1 FROM equity_points LIMIT 1").fetchone()
        return positions is None and trades is None and equity_points is None

    def _metadata_value(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM store_metadata WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def _set_metadata(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO store_metadata (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def _initialize_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS engine_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    initialized_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    cash REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS store_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    quantity REAL NOT NULL,
                    average_price REAL NOT NULL,
                    last_price REAL NOT NULL,
                    target_weight REAL NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    notional REAL NOT NULL,
                    rationale TEXT NOT NULL,
                    explanation TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
                CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);

                CREATE TABLE IF NOT EXISTS equity_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    equity REAL NOT NULL,
                    cash REAL NOT NULL,
                    gross_exposure REAL NOT NULL,
                    net_exposure REAL NOT NULL,
                    spy_price REAL NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_equity_points_timestamp ON equity_points(timestamp);

                CREATE TABLE IF NOT EXISTS signals (
                    rank INTEGER PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    score REAL NOT NULL,
                    price REAL NOT NULL,
                    news_sentiment REAL NOT NULL,
                    momentum_20d REAL NOT NULL,
                    reversal_5d REAL NOT NULL,
                    volatility_20d REAL NOT NULL,
                    avg_dollar_volume_20d REAL NOT NULL,
                    target_weight REAL NOT NULL DEFAULT 0,
                    action TEXT NOT NULL,
                    rationale TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                INSERT INTO store_metadata (key, value)
                VALUES ('schema_version', ?)
                ON CONFLICT(key) DO NOTHING
                """,
                (str(SCHEMA_VERSION),),
            )
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn


def _encode_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _rebase_state_to_starting_equity(state: EngineState, target_equity: float) -> EngineState:
    if target_equity <= 0:
        return state

    baseline_equity = _state_equity(state)
    if state.equity_curve:
        baseline_equity = state.equity_curve[0].equity
    if baseline_equity <= 0:
        return state

    scale = target_equity / baseline_equity
    payload = state.model_dump(mode="json")
    payload["cash"] *= scale

    for position in payload["positions"].values():
        position["quantity"] *= scale

    for trade in payload["trades"]:
        trade["quantity"] *= scale
        trade["notional"] *= scale

    for point in payload["equity_curve"]:
        point["equity"] *= scale
        point["cash"] *= scale
        point["gross_exposure"] *= scale
        point["net_exposure"] *= scale

    return EngineState.model_validate(payload)


def _state_equity(state: EngineState) -> float:
    equity = state.cash
    for position in state.positions.values():
        price = position.get("last_price", position["average_price"])
        equity += position["quantity"] * price
    return equity
