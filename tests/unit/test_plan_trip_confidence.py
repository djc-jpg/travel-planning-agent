"""Plan-trip confidence integration tests."""

from __future__ import annotations

from app.application.context import AppContext
from app.application.contracts import TripRequest
from app.application.plan_trip import plan_trip


class _SessionStore:
    backend = "test"

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    def get(self, session_id: str):
        return self._data.get(session_id)

    def save(self, session_id: str, state: dict) -> None:
        self._data[session_id] = state


class _DoneGraph:
    def invoke(self, state: dict) -> dict:
        next_state = dict(state)
        next_state["status"] = "done"
        next_state["repair_attempts"] = 0
        next_state["validation_issues"] = []
        next_state["final_itinerary"] = {
            "city": "杭州",
            "days": [
                {
                    "day_number": 1,
                    "schedule": [
                        {
                            "is_backup": False,
                            "poi": {
                                "name": "西湖",
                                "metadata_source": "tool_data",
                                "ticket_price": 60.0,
                                "reservation_required": True,
                                "open_hours": "09:00-17:00",
                                "closed_rules": "no closure",
                                "fact_sources": {
                                    "ticket_price_source_type": "verified",
                                    "reservation_required_source_type": "curated",
                                    "open_hours_source_type": "verified",
                                    "closed_rules_source_type": "verified",
                                },
                            },
                        }
                    ],
                }
            ],
            "assumptions": [],
        }
        next_state.setdefault("messages", [])
        next_state["messages"].append({"role": "assistant", "content": "ok"})
        return next_state


class _DoneGraphLowConfidence:
    def invoke(self, state: dict) -> dict:
        next_state = dict(state)
        next_state["status"] = "done"
        next_state["repair_attempts"] = 0
        next_state["validation_issues"] = []
        next_state["final_itinerary"] = {
            "city": "杭州",
            "days": [
                {
                    "day_number": 1,
                    "schedule": [
                        {
                            "is_backup": False,
                            "notes": "cluster=c1 | routing_confidence=0.40 | buffer=20m",
                            "poi": {
                                "name": "西湖",
                                "metadata_source": "tool_data",
                                "ticket_price": 60.0,
                                "reservation_required": True,
                                "open_hours": "09:00-17:00",
                                "closed_rules": "no closure",
                                "fact_sources": {
                                    "ticket_price_source_type": "verified",
                                    "reservation_required_source_type": "verified",
                                    "open_hours_source_type": "verified",
                                    "closed_rules_source_type": "verified",
                                },
                            },
                        }
                    ],
                }
            ],
            "assumptions": [],
        }
        next_state.setdefault("messages", [])
        next_state["messages"].append({"role": "assistant", "content": "ok"})
        return next_state


class _DoneGraphMissingFactSources:
    def invoke(self, state: dict) -> dict:
        next_state = dict(state)
        next_state["status"] = "done"
        next_state["repair_attempts"] = 0
        next_state["validation_issues"] = []
        next_state["final_itinerary"] = {
            "city": "杭州",
            "days": [
                {
                    "day_number": 1,
                    "schedule": [
                        {
                            "is_backup": False,
                            "poi": {
                                "name": "西湖",
                                "metadata_source": "tool_data",
                                "ticket_price": 60.0,
                                "reservation_required": True,
                                "open_hours": "09:00-17:00",
                                "closed_rules": "以公告为准",
                            },
                        }
                    ],
                }
            ],
            "assumptions": [],
        }
        next_state.setdefault("messages", [])
        next_state["messages"].append({"role": "assistant", "content": "ok"})
        return next_state


class _DoneGraphWrongDate:
    def invoke(self, state: dict) -> dict:
        next_state = dict(state)
        next_state["status"] = "done"
        next_state["repair_attempts"] = 0
        next_state["validation_issues"] = []
        next_state["final_itinerary"] = {
            "city": "杭州",
            "days": [
                {
                    "day_number": 1,
                    "date": "2026-02-21",
                    "schedule": [
                        {
                            "is_backup": False,
                            "poi": {
                                "name": "西湖",
                                "metadata_source": "tool_data",
                                "ticket_price": 60.0,
                                "reservation_required": True,
                                "open_hours": "09:00-17:00",
                                "closed_rules": "no closure",
                                "fact_sources": {
                                    "ticket_price_source_type": "verified",
                                    "reservation_required_source_type": "verified",
                                    "open_hours_source_type": "verified",
                                    "closed_rules_source_type": "verified",
                                },
                            },
                        }
                    ],
                },
                {
                    "day_number": 2,
                    "date": "2026-02-22",
                    "schedule": [],
                },
            ],
            "assumptions": [],
        }
        next_state.setdefault("messages", [])
        next_state["messages"].append({"role": "assistant", "content": "ok"})
        return next_state


def test_plan_trip_confidence_uses_fixture_cap_and_breakdown(monkeypatch):
    monkeypatch.setenv("ROUTING_PROVIDER", "fixture")
    ctx = AppContext(
        session_store=_SessionStore(),
        graph_factory=_DoneGraph,
        engine_version="v2",
        strict_required_fields=False,
        llm=None,
        cache={},
        key_manager=None,
        logger=None,
    )

    result = plan_trip(
        TripRequest(
            message="去杭州玩一天，2026-04-01",
            constraints={
                "city": "杭州",
                "days": 1,
                "date_start": "2026-04-01",
                "date_end": "2026-04-01",
            },
        ),
        ctx,
    )

    assert result.status.value == "done"
    assert result.itinerary is not None
    assert result.itinerary["days"][0]["date"] == "2026-04-01"
    assert result.confidence_score is not None
    assert result.confidence_score <= 0.7
    assert result.itinerary["confidence_score"] <= 0.7
    assert result.itinerary["routing_source"] == "fixture"
    assert result.itinerary["verified_fact_ratio"] > 0.5
    assert isinstance(result.itinerary.get("confidence_breakdown"), dict)
    assert result.run_fingerprint is not None
    assert result.run_fingerprint.run_mode.value == "DEGRADED"
    assert result.run_fingerprint.route_provider == "fixture"
    assert result.run_fingerprint.trace_id == result.trace_id


def test_plan_trip_marks_fallback_fixture_from_low_routing_confidence(monkeypatch):
    monkeypatch.setenv("ROUTING_PROVIDER", "real")
    ctx = AppContext(
        session_store=_SessionStore(),
        graph_factory=_DoneGraphLowConfidence,
        engine_version="v2",
        strict_required_fields=False,
        llm=None,
        cache={},
        key_manager=None,
        logger=None,
    )

    result = plan_trip(
        TripRequest(
            message="去杭州玩一天，2026-04-01",
            constraints={
                "city": "杭州",
                "days": 1,
                "date_start": "2026-04-01",
                "date_end": "2026-04-01",
            },
        ),
        ctx,
    )

    assert result.status.value == "done"
    assert result.itinerary is not None
    assert result.itinerary["routing_source"] == "fallback_fixture"
    assert result.itinerary["fallback_count"] >= 1
    assert result.confidence_score is not None
    assert result.confidence_score <= 0.65
    assert result.run_fingerprint is not None
    assert result.run_fingerprint.route_provider == "fallback_fixture"


def test_plan_trip_overrides_itinerary_dates_with_requested_start(monkeypatch):
    monkeypatch.setenv("ROUTING_PROVIDER", "fixture")
    ctx = AppContext(
        session_store=_SessionStore(),
        graph_factory=_DoneGraphWrongDate,
        engine_version="v2",
        strict_required_fields=False,
        llm=None,
        cache={},
        key_manager=None,
        logger=None,
    )

    result = plan_trip(
        TripRequest(
            message="去杭州玩两天，2026-04-01",
            constraints={
                "city": "杭州",
                "days": 2,
                "date_start": "2026-04-01",
                "date_end": "2026-04-02",
            },
        ),
        ctx,
    )

    assert result.status.value == "done"
    assert result.itinerary is not None
    days = result.itinerary.get("days", [])
    assert days[0]["date"] == "2026-04-01"
    assert days[1]["date"] == "2026-04-02"


def test_plan_trip_overrides_dates_when_start_uses_slash_format(monkeypatch):
    monkeypatch.setenv("ROUTING_PROVIDER", "fixture")
    ctx = AppContext(
        session_store=_SessionStore(),
        graph_factory=_DoneGraphWrongDate,
        engine_version="v2",
        strict_required_fields=False,
        llm=None,
        cache={},
        key_manager=None,
        logger=None,
    )

    result = plan_trip(
        TripRequest(
            message="去杭州玩两天，2026/04/01",
            constraints={
                "city": "杭州",
                "days": 2,
                "date_start": "2026/04/01",
                "date_end": "2026/04/02",
            },
        ),
        ctx,
    )

    assert result.status.value == "done"
    assert result.itinerary is not None
    days = result.itinerary.get("days", [])
    assert days[0]["date"] == "2026-04-01"
    assert days[1]["date"] == "2026-04-02"


def test_plan_trip_marks_missing_fact_sources_as_unknown(monkeypatch):
    monkeypatch.setenv("ROUTING_PROVIDER", "fixture")
    ctx = AppContext(
        session_store=_SessionStore(),
        graph_factory=_DoneGraphMissingFactSources,
        engine_version="v2",
        strict_required_fields=False,
        llm=None,
        cache={},
        key_manager=None,
        logger=None,
    )

    result = plan_trip(
        TripRequest(
            message="去杭州玩一天，2026-04-01",
            constraints={
                "city": "杭州",
                "days": 1,
                "date_start": "2026-04-01",
                "date_end": "2026-04-01",
            },
        ),
        ctx,
    )

    assert result.status.value == "done"
    assert result.itinerary is not None
    item = result.itinerary["days"][0]["schedule"][0]
    fact_sources = item["poi"]["fact_sources"]
    assert fact_sources["ticket_price_source_type"] == "unknown"
    assert fact_sources["reservation_required_source_type"] == "unknown"
    assert fact_sources["open_hours_source_type"] == "unknown"
    assert fact_sources["closed_rules_source_type"] == "unknown"
    assert set(result.itinerary.get("unknown_fields", [])) == {
        "西湖.ticket_price",
        "西湖.reservation_required",
        "西湖.open_hours",
        "西湖.closed_rules",
    }
    assert result.itinerary.get("verified_fact_ratio") == 0.0
