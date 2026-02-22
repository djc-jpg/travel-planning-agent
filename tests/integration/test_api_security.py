from fastapi.testclient import TestClient

import app.api.main as api_main
from app.persistence.models import PlanExportRecord, SessionHistoryItem, SessionSummaryItem

client = TestClient(api_main.app)


def _require_api_auth(monkeypatch):
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED_API", "false")


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
    assert "plan_metrics" in ok.json()
    assert "runtime_flags" in ok.json()


def test_diagnostics_enabled_without_token_returns_503(monkeypatch):
    monkeypatch.setenv("ENABLE_DIAGNOSTICS", "true")
    monkeypatch.delenv("DIAGNOSTICS_TOKEN", raising=False)

    resp = client.get("/diagnostics")
    assert resp.status_code == 503


def test_metrics_endpoint_available_without_diagnostics_token(monkeypatch):
    monkeypatch.delenv("ENABLE_DIAGNOSTICS", raising=False)
    monkeypatch.delenv("DIAGNOSTICS_TOKEN", raising=False)

    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_requests" in body
    assert "tool_calls" in body


def test_plan_empty_message_validation():
    resp = client.post("/plan", json={"message": ""})
    assert resp.status_code == 422


def test_api_bearer_auth_for_plan(monkeypatch):
    _require_api_auth(monkeypatch)
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
    _require_api_auth(monkeypatch)
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
    def _timeout(*_args, **_kwargs):
        raise api_main.GraphTimeoutError(1)

    monkeypatch.setattr(api_main, "execute_plan", _timeout)

    resp = client.post("/plan", json={"message": "beijing 3 day trip"})
    assert resp.status_code == 504


def test_plan_internal_error_returns_500(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(api_main, "execute_plan", _boom)

    resp = client.post("/plan", json={"message": "shanghai 2 day trip"})
    assert resp.status_code == 500


def test_history_endpoint_requires_api_bearer(monkeypatch):
    _require_api_auth(monkeypatch)
    monkeypatch.setenv("API_BEARER_TOKEN", "api_token")

    missing = client.get("/sessions/chat_1/history")
    assert missing.status_code == 401

    wrong = client.get(
        "/sessions/chat_1/history",
        headers={"Authorization": "Bearer wrong"},
    )
    assert wrong.status_code == 403


def test_sessions_endpoint_requires_api_bearer(monkeypatch):
    _require_api_auth(monkeypatch)
    monkeypatch.setenv("API_BEARER_TOKEN", "api_token")

    missing = client.get("/sessions")
    assert missing.status_code == 401

    wrong = client.get(
        "/sessions",
        headers={"Authorization": "Bearer wrong"},
    )
    assert wrong.status_code == 403


def test_sessions_endpoint_success(monkeypatch):
    class _Repo:
        backend = "test"

        def list_sessions(self, limit: int = 20):
            _ = limit
            return [
                SessionSummaryItem(
                    session_id="chat_1",
                    updated_at="2026-02-21T01:00:00Z",
                    last_status="done",
                    last_trace_id="trace_1",
                )
            ]

        def list_session_history(self, session_id: str, limit: int = 20):
            _ = (session_id, limit)
            return []

        def get_plan_export(self, request_id: str):
            _ = request_id
            return None

    _require_api_auth(monkeypatch)
    monkeypatch.setenv("API_BEARER_TOKEN", "api_token")
    monkeypatch.setattr(api_main._app_ctx, "persistence_repo", _Repo(), raising=False)

    resp = client.get(
        "/sessions?limit=5",
        headers={"Authorization": "Bearer api_token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["session_id"] == "chat_1"
    assert body["items"][0]["last_status"] == "done"


def test_sessions_endpoint_empty_list(monkeypatch):
    class _Repo:
        backend = "test"

        def list_sessions(self, limit: int = 20):
            _ = limit
            return []

        def list_session_history(self, session_id: str, limit: int = 20):
            _ = (session_id, limit)
            return []

        def get_plan_export(self, request_id: str):
            _ = request_id
            return None

    _require_api_auth(monkeypatch)
    monkeypatch.setenv("API_BEARER_TOKEN", "api_token")
    monkeypatch.setattr(api_main._app_ctx, "persistence_repo", _Repo(), raising=False)

    resp = client.get(
        "/sessions?limit=5",
        headers={"Authorization": "Bearer api_token"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []


def test_history_and_export_endpoints_success(monkeypatch):
    class _Repo:
        backend = "test"

        def list_sessions(self, limit: int = 20):
            _ = limit
            return []

        def list_session_history(self, session_id: str, limit: int = 20):
            _ = limit
            if session_id != "chat_1":
                return []
            return [
                SessionHistoryItem(
                    request_id="req_1",
                    session_id=session_id,
                    trace_id="trace_1",
                    message="beijing 2 day trip",
                    status="done",
                    degrade_level="L1",
                    confidence_score=0.8,
                    run_fingerprint={"run_mode": "DEGRADED"},
                    created_at="2026-02-21T01:00:00Z",
                )
            ]

        def get_plan_export(self, request_id: str):
            if request_id != "req_1":
                return None
            return PlanExportRecord(
                request_id="req_1",
                session_id="chat_1",
                trace_id="trace_1",
                message="beijing 2 day trip",
                constraints={"city": "beijing"},
                user_profile={"themes": ["history"]},
                metadata={},
                status="done",
                degrade_level="L1",
                confidence_score=0.8,
                run_fingerprint={"run_mode": "DEGRADED"},
                itinerary={"city": "beijing", "days": []},
                issues=[],
                next_questions=[],
                field_evidence={},
                metrics={"verified_fact_ratio": 0.8},
                created_at="2026-02-21T01:00:00Z",
                artifacts=[],
            )

    _require_api_auth(monkeypatch)
    monkeypatch.setenv("API_BEARER_TOKEN", "api_token")
    monkeypatch.setattr(api_main._app_ctx, "persistence_repo", _Repo(), raising=False)

    history = client.get(
        "/sessions/chat_1/history",
        headers={"Authorization": "Bearer api_token"},
    )
    assert history.status_code == 200
    history_body = history.json()
    assert history_body["session_id"] == "chat_1"
    assert len(history_body["items"]) == 1
    assert history_body["items"][0]["request_id"] == "req_1"

    exported = client.get(
        "/plans/req_1/export",
        headers={"Authorization": "Bearer api_token"},
    )
    assert exported.status_code == 200
    export_body = exported.json()
    assert export_body["request_id"] == "req_1"
    assert export_body["status"] == "done"
    assert export_body["metrics"]["verified_fact_ratio"] == 0.8

    markdown = client.get(
        "/plans/req_1/export?format=markdown",
        headers={"Authorization": "Bearer api_token"},
    )
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "# Trip Plan Export" in markdown.text


def test_export_endpoint_not_found(monkeypatch):
    class _Repo:
        backend = "test"

        def list_sessions(self, limit: int = 20):
            _ = limit
            return []

        def list_session_history(self, session_id: str, limit: int = 20):
            _ = (session_id, limit)
            return []

        def get_plan_export(self, request_id: str):
            _ = request_id
            return None

    _require_api_auth(monkeypatch)
    monkeypatch.setenv("API_BEARER_TOKEN", "api_token")
    monkeypatch.setattr(api_main._app_ctx, "persistence_repo", _Repo(), raising=False)

    resp = client.get(
        "/plans/not_found/export",
        headers={"Authorization": "Bearer api_token"},
    )
    assert resp.status_code == 404


def test_api_fail_closed_when_auth_not_configured(monkeypatch):
    _require_api_auth(monkeypatch)
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)

    resp = client.post("/plan", json={"message": "beijing 3 day trip"})
    assert resp.status_code == 503


def test_export_endpoint_rejects_unknown_format(monkeypatch):
    class _Repo:
        backend = "test"

        def list_sessions(self, limit: int = 20):
            _ = limit
            return []

        def list_session_history(self, session_id: str, limit: int = 20):
            _ = (session_id, limit)
            return []

        def get_plan_export(self, request_id: str):
            if request_id != "req_1":
                return None
            return PlanExportRecord(
                request_id="req_1",
                session_id="chat_1",
                trace_id="trace_1",
                message="beijing 2 day trip",
                constraints={},
                user_profile={},
                metadata={},
                status="done",
                degrade_level="L1",
                confidence_score=0.8,
                run_fingerprint={},
                itinerary={"city": "beijing", "days": []},
                issues=[],
                next_questions=[],
                field_evidence={},
                metrics={},
                created_at="2026-02-21T01:00:00Z",
                artifacts=[],
            )

    _require_api_auth(monkeypatch)
    monkeypatch.setenv("API_BEARER_TOKEN", "api_token")
    monkeypatch.setattr(api_main._app_ctx, "persistence_repo", _Repo(), raising=False)

    resp = client.get(
        "/plans/req_1/export?format=html",
        headers={"Authorization": "Bearer api_token"},
    )
    assert resp.status_code == 400


def test_export_openapi_declares_markdown_variant():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200

    path_item = resp.json()["paths"]["/plans/{request_id}/export"]["get"]
    content = path_item["responses"]["200"]["content"]
    assert "application/json" in content
    assert "text/markdown" in content
    assert content["text/markdown"]["schema"]["type"] == "string"
