from fastapi.testclient import TestClient

import app.api.main as api_main

client = TestClient(api_main.app)


def test_diagnostics_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_DIAGNOSTICS", raising=False)
    monkeypatch.delenv("DIAGNOSTICS_TOKEN", raising=False)

    resp = client.get("/diagnostics")
    assert resp.status_code == 404


def test_diagnostics_bearer_auth(monkeypatch):
    monkeypatch.setenv("ENABLE_DIAGNOSTICS", "true")
    monkeypatch.setenv("DIAGNOSTICS_TOKEN", "diag_token_value")

    missing = client.get("/diagnostics")
    assert missing.status_code == 401

    wrong = client.get("/diagnostics", headers={"Authorization": "Bearer wrong"})
    assert wrong.status_code == 403

    ok = client.get("/diagnostics", headers={"Authorization": "Bearer diag_token_value"})
    assert ok.status_code == 200
    assert "tools" in ok.json()


def test_diagnostics_enabled_without_token_returns_503(monkeypatch):
    monkeypatch.setenv("ENABLE_DIAGNOSTICS", "true")
    monkeypatch.delenv("DIAGNOSTICS_TOKEN", raising=False)

    resp = client.get("/diagnostics")
    assert resp.status_code == 503


def test_plan_empty_message_validation():
    resp = client.post("/plan", json={"message": ""})
    assert resp.status_code == 422


def test_api_bearer_auth_for_plan(monkeypatch):
    monkeypatch.setenv("API_BEARER_TOKEN", "api_token")

    missing = client.post("/plan", json={"message": "beijing 3 day trip"})
    assert missing.status_code == 401

    wrong = client.post(
        "/plan",
        json={"message": "beijing 3 day trip"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert wrong.status_code == 403

    ok = client.post(
        "/plan",
        json={"message": "beijing 3 day trip"},
        headers={"Authorization": "Bearer api_token"},
    )
    assert ok.status_code in {200, 422}


def test_api_bearer_auth_for_chat(monkeypatch):
    monkeypatch.setenv("API_BEARER_TOKEN", "api_token")

    missing = client.post("/chat", json={"session_id": "chat_1", "message": "hello"})
    assert missing.status_code == 401

    ok = client.post(
        "/chat",
        json={"session_id": "chat_1", "message": "hello"},
        headers={"Authorization": "Bearer api_token"},
    )
    assert ok.status_code in {200, 422}


def test_chat_invalid_session_id_validation():
    resp = client.post("/chat", json={"session_id": "bad id!", "message": "hello"})
    assert resp.status_code == 422


def test_plan_timeout_returns_504(monkeypatch):
    monkeypatch.setattr(api_main, "_get_graph", lambda: object())

    def _timeout(*_args, **_kwargs):
        raise api_main.GraphTimeoutError(1)

    monkeypatch.setattr(api_main, "_invoke_with_timeout", _timeout)

    resp = client.post("/plan", json={"message": "beijing 3 day trip"})
    assert resp.status_code == 504


def test_plan_internal_error_returns_500(monkeypatch):
    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(api_main, "_get_graph", _boom)

    resp = client.post("/plan", json={"message": "shanghai 2 day trip"})
    assert resp.status_code == 500
