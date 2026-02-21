"""Service-layer tests for execute_plan use-case."""

from __future__ import annotations

from app.application.contracts import TripResult, TripStatus
import app.services.plan_service as plan_service


def test_execute_plan_builds_trip_request(monkeypatch):
    captured = {}

    def _fake_plan_trip(request, ctx):
        captured["request"] = request
        captured["ctx"] = ctx
        return TripResult(status=TripStatus.DONE, message="ok", itinerary={"city": "贵阳", "days": []})

    monkeypatch.setattr(plan_service, "plan_trip", _fake_plan_trip)
    ctx = object()
    result = plan_service.execute_plan(
        ctx=ctx,
        message="贵阳两天",
        session_id="s-1",
        constraints={
            "city": "贵阳",
            "days": 2,
            "date_start": "2026-03-12",
            "date_end": "2026-03-16",
        },
        user_profile={"themes": ["美食"]},
        metadata={"source": "test"},
        debug=False,
    )

    assert result.status == TripStatus.DONE
    req = captured["request"]
    assert captured["ctx"] is ctx
    assert req.message == "贵阳两天"
    assert req.session_id == "s-1"
    assert req.constraints["city"] == "贵阳"
    assert req.constraints["date_start"] == "2026-03-12"
    assert req.constraints["date_end"] == "2026-03-16"
    assert req.user_profile["themes"] == ["美食"]
    assert req.metadata["source"] == "test"


def test_execute_plan_applies_user_itinerary_projection_by_default(monkeypatch):
    def _fake_plan_trip(_request, _ctx):
        return TripResult(
            status=TripStatus.DONE,
            message="ok",
            itinerary={
                "city": "贵阳",
                "days": [
                    {
                        "day_number": 1,
                        "schedule": [
                            {
                                "poi": {"id": "p1", "name": "贵州省博物馆", "cluster": "geo:1"},
                                "notes": "建议提前预约 | routing_confidence=0.72 | cluster=geo:1",
                                "is_backup": False,
                            }
                        ],
                        "backups": [],
                    }
                ],
                "unknown_fields": ["x"],
                "confidence_breakdown": {"raw": 0.7},
            },
        )

    monkeypatch.setattr(plan_service, "plan_trip", _fake_plan_trip)
    result = plan_service.execute_plan(ctx=object(), message="贵阳两天", debug=False)
    assert result.itinerary is not None
    assert "unknown_fields" not in result.itinerary
    assert "confidence_breakdown" not in result.itinerary
    note = result.itinerary["days"][0]["schedule"][0].get("notes", "")
    assert "routing_confidence=" not in note
    assert "cluster=" not in note


def test_execute_plan_normalizes_machine_message_for_readability(monkeypatch):
    def _fake_plan_trip(_request, _ctx):
        return TripResult(
            status=TripStatus.DONE,
            message="chengdu 3d executable itinerary | day1:锦里->武侯祠",
            itinerary={"city": "成都", "days": []},
        )

    monkeypatch.setattr(plan_service, "plan_trip", _fake_plan_trip)
    result = plan_service.execute_plan(ctx=object(), message="成都三天", debug=False)

    assert result.message == "行程已生成，可在下方查看每天安排。"
