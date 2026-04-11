from app.services.explanations import TradeExplanationService


def test_explanation_service_falls_back_without_groq(monkeypatch):
    monkeypatch.setattr("app.config.settings.enable_trade_explanations", False)
    service = TradeExplanationService()

    explanation = service.explain_trade(
        symbol="AAPL",
        side="buy",
        quantity=10,
        price=150,
        notional=1500,
        rationale="mom=3.00%, rev=1.00%, news=0.30, vol=20.00%",
    )

    assert explanation.startswith("Buy AAPL")
    assert explanation.endswith(".")
