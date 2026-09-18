from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


def test_health_stays_public_when_token_enabled(monkeypatch):
    monkeypatch.setattr(main, "_API_TOKEN", "test-secret")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth_check_rejects_missing_token(monkeypatch):
    monkeypatch.setattr(main, "_API_TOKEN", "test-secret")
    response = client.get("/auth/check")
    assert response.status_code == 401


def test_auth_check_accepts_matching_bearer_token(monkeypatch):
    monkeypatch.setattr(main, "_API_TOKEN", "test-secret")
    response = client.get(
        "/auth/check",
        headers={"Authorization": "Bearer test-secret"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth_is_disabled_when_token_empty(monkeypatch):
    monkeypatch.setattr(main, "_API_TOKEN", "")
    response = client.get("/auth/check")
    assert response.status_code == 200
