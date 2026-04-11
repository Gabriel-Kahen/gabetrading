import pandas as pd

from app.services.strategy import StrategyService


def _make_history(symbol: str, closes: list[float], volumes: list[int]) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    return pd.concat(
        {
            symbol: pd.DataFrame(
                {
                    "Close": closes,
                    "Volume": volumes,
                },
                index=index,
            )
        },
        axis=1,
    )


def test_strategy_generates_long_signal_for_strong_symbol():
    history = _make_history("AAA", list(range(100, 140)), [2_000_000] * 40)
    intraday_history = _make_history("AAA", list(range(120, 180)), [500_000] * 60)
    signals = StrategyService().generate_signals(
        symbols=["AAA"],
        history=history,
        intraday_history=intraday_history,
        prices={"AAA": 179.0},
        news_scores={"AAA": 0.5},
    )
    assert len(signals) == 1
    assert signals[0].score > 0
    assert signals[0].action == "long"
    assert signals[0].target_weight > 0
