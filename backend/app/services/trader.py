from __future__ import annotations

from threading import Lock

from app.models.schemas import PortfolioSnapshot, Signal
from app.services.explanations import TradeExplanationService
from app.services.market_data import MarketDataService
from app.services.news import NewsService
from app.services.portfolio import PortfolioService
from app.services.strategy import StrategyService
from app.services.universe import load_sp500_symbols


class TradingOrchestrator:
    def __init__(self) -> None:
        self.market_data = MarketDataService()
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
            return portfolio, signals
