from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint(monkeypatch):
    monkeypatch.setattr("app.config.settings.auto_run_on_start", False)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
