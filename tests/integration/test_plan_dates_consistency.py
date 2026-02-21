"""Integration test for date consistency between input constraints and itinerary."""

from __future__ import annotations

from app.application.context import make_app_context
from app.application.contracts import TripRequest
from app.application.plan_trip import plan_trip


def test_itinerary_dates_follow_date_start_constraint(monkeypatch):
    monkeypatch.setenv("ENGINE_VERSION", "v2")
    monkeypatch.setenv("STRICT_REQUIRED_FIELDS", "false")

    ctx = make_app_context()
    result = plan_trip(
        TripRequest(
            message="我想去北京玩2天，历史文化路线",
            constraints={
                "city": "北京",
                "days": 2,
                "date_start": "2026-03-12",
                "date_end": "2026-03-16",
            },
            user_profile={"themes": ["历史古迹"]},
            metadata={
                "source": "integration_test",
                "field_sources": {
                    "city": "user_form",
                    "days": "user_form",
                    "date_start": "user_form",
                    "date_end": "user_form",
                },
            },
        ),
        ctx,
    )

    assert result.status.value == "done"
    assert result.itinerary is not None
    days = result.itinerary.get("days", [])
    assert len(days) >= 2
    assert days[0].get("date") == "2026-03-12"
    assert days[1].get("date") == "2026-03-13"

