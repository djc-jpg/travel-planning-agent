"""City hotplug integration test."""

from __future__ import annotations

from app.application.context import make_app_context
from app.application.contracts import TripRequest
from app.application.plan_trip import plan_trip


def test_city_hotplug():
    ctx = make_app_context()
    result = plan_trip(
        TripRequest(
            message="testcity 两天行程，轻松一点",
            constraints={
                "city": "testcity",
                "days": 2,
                "date_start": "2026-05-01",
                "date_end": "2026-05-02",
            },
        ),
        ctx,
    )

    assert result.status.value == "done"
    assert result.itinerary is not None
    assert str(result.itinerary.get("city", "")).lower() == "testcity"
    assert result.itinerary.get("degrade_level") in {"L1", "L2"}

