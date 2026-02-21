"""Itinerary presentation filtering tests."""

from __future__ import annotations

from app.services.itinerary_presenter import present_itinerary


def _fixture_itinerary() -> dict:
    return {
        "city": "贵阳",
        "days": [
            {
                "day_number": 1,
                "schedule": [
                    {
                        "poi": {
                            "id": "p1",
                            "name": "贵州省博物馆",
                            "metadata_source": "tool_data",
                            "cluster": "geo:1",
                            "fact_sources": {"ticket_price": "data"},
                        },
                        "notes": "建议提前预约 | cluster=geo:1 | routing_confidence=0.72 | closed_rules=以公告为准",
                        "travel_minutes": 12.0,
                        "is_backup": False,
                    }
                ],
                "backups": [],
            }
        ],
        "unknown_fields": ["贵州省博物馆.open_hours"],
        "routing_source": "fixture",
        "fallback_count": 0,
        "verified_fact_ratio": 0.75,
        "confidence_breakdown": {"raw": 0.7},
        "trace_id": "trace_x",
        "degrade_level": "L1",
        "confidence_score": 0.7,
        "budget_breakdown": {"tickets": 0.0, "routing_confidence": 0.72},
        "budget_source_breakdown": {"tickets": "verified", "local_transport": "heuristic"},
        "budget_confidence_breakdown": {"tickets": 0.95, "local_transport": 0.55},
        "budget_confidence_score": 0.81,
        "budget_as_of": "2026-02-21",
    }


def test_present_itinerary_hides_debug_fields_by_default():
    payload = present_itinerary(_fixture_itinerary(), debug=False)

    assert payload is not None
    assert "unknown_fields" not in payload
    assert "routing_source" not in payload
    assert "confidence_breakdown" not in payload
    assert payload["budget_breakdown"].get("routing_confidence") is None
    assert payload["budget_source_breakdown"]["tickets"] == "verified"
    assert payload["budget_confidence_breakdown"]["tickets"] == 0.95
    assert payload["budget_confidence_score"] == 0.81
    assert payload["budget_as_of"] == "2026-02-21"
    item = payload["days"][0]["schedule"][0]
    assert "routing_confidence=" not in item.get("notes", "")
    assert item.get("notes") == "建议提前预约"
    assert "metadata_source" not in item["poi"]
    assert "cluster" not in item["poi"]
    assert "fact_sources" not in item["poi"]


def test_present_itinerary_keeps_debug_payload_when_enabled():
    original = _fixture_itinerary()
    payload = present_itinerary(original, debug=True)

    assert payload == original
    assert payload is not original


def test_present_itinerary_strips_fullwidth_debug_separators():
    payload = _fixture_itinerary()
    payload["days"][0]["schedule"][0]["notes"] = (
        "建议提前预约 ｜ cluster=geo:2 ｜ routing_confidence=0.61 ｜ fallback_schedule"
    )

    shown = present_itinerary(payload, debug=False)
    assert shown is not None
    assert shown["days"][0]["schedule"][0].get("notes") == "建议提前预约"
