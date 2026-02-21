"""API debug toggle tests for itinerary payload shape."""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.api.main as api_main
from app.application.contracts import TripResult, TripStatus
import app.services.plan_service as plan_service


client = TestClient(api_main.app)


def _result_with_debug_fields() -> TripResult:
    return TripResult(
        status=TripStatus.DONE,
        message="ok",
        session_id="s1",
        request_id="r1",
        trace_id="t1",
        degrade_level="L1",
        confidence_score=0.7,
        itinerary={
            "city": "贵阳",
            "days": [
                {
                    "day_number": 1,
                    "schedule": [
                        {
                            "poi": {
                                "id": "p1",
                                "name": "贵州省博物馆",
                                "cluster": "geo:1",
                                "metadata_source": "tool_data",
                                "fact_sources": {"ticket_price": "data"},
                            },
                            "notes": "建议提前预约 | cluster=geo:1 | routing_confidence=0.72",
                            "travel_minutes": 12.0,
                            "is_backup": False,
                        }
                    ],
                    "backups": [],
                }
            ],
            "routing_source": "fixture",
            "confidence_breakdown": {"raw": 0.7},
            "unknown_fields": ["x"],
        },
    )


def test_plan_hides_debug_itinerary_by_default(monkeypatch):
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    monkeypatch.setattr(plan_service, "plan_trip", lambda *_args, **_kwargs: _result_with_debug_fields())

    resp = client.post("/plan", json={"message": "贵阳两天"})
    assert resp.status_code == 200
    itinerary = resp.json()["itinerary"]
    assert "unknown_fields" not in itinerary
    assert "confidence_breakdown" not in itinerary
    notes = itinerary["days"][0]["schedule"][0].get("notes", "")
    assert "routing_confidence=" not in notes
    assert "cluster=" not in notes


def test_plan_returns_debug_itinerary_when_enabled(monkeypatch):
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    monkeypatch.setattr(plan_service, "plan_trip", lambda *_args, **_kwargs: _result_with_debug_fields())

    resp = client.post("/plan?debug=true", json={"message": "贵阳两天"})
    assert resp.status_code == 200
    itinerary = resp.json()["itinerary"]
    assert "unknown_fields" in itinerary
    assert "confidence_breakdown" in itinerary
    notes = itinerary["days"][0]["schedule"][0].get("notes", "")
    assert "routing_confidence=" in notes
    assert "cluster=" in notes
