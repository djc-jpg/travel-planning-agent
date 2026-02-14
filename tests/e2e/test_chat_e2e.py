"""End-to-end chat flow smoke test."""

from fastapi.testclient import TestClient

from app.api.main import app


def test_chat_end_to_end_smoke():
    client = TestClient(app)
    session_id = "e2e-session-1"

    first = client.post("/chat", json={"session_id": session_id, "message": "我想去北京旅游"})
    assert first.status_code == 200
    status = first.json()["status"]
    assert status in ("clarifying", "done")

    second = client.post("/chat", json={"session_id": session_id, "message": "3天，预算每天500，喜欢历史"})
    assert second.status_code == 200
    assert second.json()["status"] in ("done", "clarifying", "planning")

