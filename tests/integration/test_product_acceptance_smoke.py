"""Product acceptance smoke tests for user-visible output and runtime fingerprint."""

from __future__ import annotations

from app.application.context import make_app_context
from app.services.plan_service import execute_plan

_DEBUG_KEYS = {
    "unknown_fields",
    "trace_id",
    "violations",
    "repair_actions",
    "verified_fact_ratio",
    "routing_source",
    "fallback_count",
    "confidence_breakdown",
    "confidence_score",
    "degrade_level",
}


def test_product_acceptance_user_payload_smoke(monkeypatch):
    monkeypatch.setenv("ENGINE_VERSION", "v2")
    monkeypatch.setenv("STRICT_REQUIRED_FIELDS", "false")
    monkeypatch.setenv("ROUTING_PROVIDER", "fixture")
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    ctx = make_app_context()
    result = execute_plan(
        ctx=ctx,
        message="北京3天旅行",
        constraints={
            "city": "北京",
            "days": 3,
            "date_start": "2026-03-12",
            "date_end": "2026-03-14",
            "budget_per_day": 500,
        },
        user_profile={"travelers_type": "couple", "themes": ["历史古迹"]},
        metadata={
            "source": "product_acceptance_smoke",
            "field_sources": {
                "city": "user_form",
                "days": "user_form",
                "date_start": "user_form",
                "date_end": "user_form",
            },
        },
        debug=False,
    )

    assert result.status.value == "done"
    assert result.run_fingerprint is not None
    assert result.run_fingerprint.run_mode.value == "DEGRADED"
    assert result.run_fingerprint.route_provider == "fixture"

    itinerary = result.itinerary or {}
    for key in _DEBUG_KEYS:
        assert key not in itinerary

    days = itinerary.get("days", [])
    assert len(days) == 3
    assert days[0].get("date") == "2026-03-12"
    assert "executable itinerary" not in str(result.message).lower()

