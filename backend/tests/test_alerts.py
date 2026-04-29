from app.services.alerts import AlertService


def test_alert_service_posts_to_discord(monkeypatch):
    calls = []
    monkeypatch.setattr("app.config.settings.discord_webhook_url", "https://discord.test/webhook")

    class Response:
        def raise_for_status(self):
            return None

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        return Response()

    monkeypatch.setattr("app.services.alerts.requests.post", fake_post)

    sent = AlertService().send("Test Alert", "Something happened", key="test")

    assert sent
    assert calls[0][0] == "https://discord.test/webhook"
    assert calls[0][1]["embeds"][0]["title"] == "Test Alert"


def test_alert_service_cools_down_duplicate_keys(monkeypatch):
    calls = []
    monkeypatch.setattr("app.config.settings.discord_webhook_url", "https://discord.test/webhook")
    monkeypatch.setattr("app.config.settings.alert_cooldown_seconds", 900)

    class Response:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "app.services.alerts.requests.post",
        lambda *args, **kwargs: calls.append((args, kwargs)) or Response(),
    )

    service = AlertService()

    assert service.send("Test Alert", "one", key="same-key")
    assert not service.send("Test Alert", "two", key="same-key")
    assert len(calls) == 1
