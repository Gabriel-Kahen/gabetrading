from __future__ import annotations

from threading import Lock

from app.models.schemas import PortfolioSnapshot, Signal
from app.config import settings
from app.services.alerts import AlertService
from app.services.explanations import TradeExplanationService
from app.services.market_data import MarketDataService
from app.services.news import NewsService
from app.services.portfolio import PortfolioService
from app.services.strategy import StrategyService
from app.services.universe import load_sp500_symbols


class TradingOrchestrator:
    def __init__(self) -> None:
        self.alerts = AlertService()
        self.market_data = MarketDataService(alert_service=self.alerts)
        self.news = NewsService()
        self.strategy = StrategyService()
        self.explanations = TradeExplanationService()
        self.portfolio = PortfolioService(explanation_service=self.explanations)
        self._symbols = load_sp500_symbols()
        self._cycle_lock = Lock()

    def run_cycle(self) -> tuple[PortfolioSnapshot, list[Signal]]:
        with self._cycle_lock:
            fetch_symbols = list(dict.fromkeys(self._symbols + ["SPY"]))
            snapshot = self.market_data.fetch_snapshot(fetch_symbols)
            news_scores = self.news.score_news(self._symbols)
            signals = self.strategy.generate_signals(
                self._symbols,
                snapshot.history,
                snapshot.intraday_history,
                snapshot.prices,
                news_scores,
            )
            portfolio = self.portfolio.rebalance(signals, snapshot.prices)
            self._alert_on_anomalous_closed_positions()
            return portfolio, signals

    def _alert_on_anomalous_closed_positions(self) -> None:
        for position in self.portfolio.get_closed_positions():
            duration_minutes = (position.closed_at - position.opened_at).total_seconds() / 60
            if duration_minutes > settings.anomaly_duration_minutes:
                continue
            if abs(position.realized_return_pct) < settings.anomaly_return_threshold_pct:
                continue
            self.alerts.send(
                "Suspicious closed-position move",
                (
                    f"{position.symbol} {position.direction} closed at "
                    f"{position.realized_return_pct:.2f}% over {duration_minutes:.1f} minutes. "
                    f"Entry ${position.average_entry_price:.2f}, exit ${position.average_exit_price:.2f}."
                ),
                key=f"closed-position:{position.symbol}:{position.opened_at.isoformat()}:{position.closed_at.isoformat()}",
            )
