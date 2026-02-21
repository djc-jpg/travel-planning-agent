"""Milestone-1 architecture convergence tests."""

from fastapi.testclient import TestClient

import app.api.main as api_main
from app.application.context import make_app_context
from app.application.contracts import TripRequest
from app.application.plan_trip import plan_trip
from app.cli import run_request as cli_run_request
from app.eval.run_eval import run_request as eval_run_request


def test_missing_required_fields_clarify_when_strict(monkeypatch):
    monkeypatch.setenv("ENGINE_VERSION", "v2")
    monkeypatch.setenv("STRICT_REQUIRED_FIELDS", "true")
    monkeypatch.setattr(api_main, "_app_ctx", make_app_context())

    client = TestClient(api_main.app)
    resp = client.post("/plan", json={"message": "帮我规划旅行"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "clarifying"
    assert body.get("next_questions")
    prompts = body["next_questions"]
    assert any("目的地城市" in item for item in prompts)
    assert any("旅行天数" in item for item in prompts)
    assert any("出发日期" in item for item in prompts)
    assert any("返程日期" in item for item in prompts)


def test_single_entry_consistency_across_api_cli_eval(monkeypatch):
    monkeypatch.setenv("ENGINE_VERSION", "v2")
    monkeypatch.setenv("STRICT_REQUIRED_FIELDS", "false")

    ctx = make_app_context()
    monkeypatch.setattr(api_main, "_app_ctx", ctx)

    message = "我想去杭州玩4天，预算每天800，主要打车，喜欢历史和美食"

    direct = plan_trip(TripRequest(message=message), ctx).model_dump(mode="json")

    client = TestClient(api_main.app)
    api_resp = client.post("/plan", json={"message": message})
    assert api_resp.status_code == 200
    api_result = api_resp.json()

    cli_result = cli_run_request(message, None, ctx).model_dump(mode="json")
    eval_result = eval_run_request(message, ctx)

    assert api_result["status"] == direct["status"] == cli_result["status"] == eval_result["status"]

    for result in (api_result, direct, cli_result, eval_result):
        itinerary = result.get("itinerary")
        assert itinerary is not None
        assert itinerary.get("city") == "杭州"
        assert len(itinerary.get("days", [])) == 4
