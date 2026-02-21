"""Plan-trip integration tests for diff-based edit patch flow."""

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
            "city": "北京",
            "days": [
                {
                    "day_number": 1,
                    "schedule": [{"is_backup": False, "poi": {"name": "新一天"}}],
                    "meal_windows": ["12:00-13:00"],
                },
                {
                    "day_number": 2,
                    "schedule": [{"is_backup": False, "poi": {"name": "颐和园"}}],
                    "meal_windows": ["12:00-13:00"],
                },
            ],
            "assumptions": [],
            "summary": "new_summary",
        }
        next_state.setdefault("messages", [])
        next_state["messages"].append({"role": "assistant", "content": "new_summary"})
        return next_state


def test_plan_trip_applies_day_level_diff_patch():
    session_store = _SessionStore()
    session_store.save(
        "s1",
        {
            "status": "done",
            "final_itinerary": {
                "city": "北京",
                "days": [
                    {
                        "day_number": 1,
                        "schedule": [{"is_backup": False, "poi": {"name": "天安门"}}],
                        "meal_windows": ["12:00-13:00"],
                    },
                    {
                        "day_number": 2,
                        "schedule": [{"is_backup": False, "poi": {"name": "故宫"}}],
                        "meal_windows": ["12:00-13:00"],
                    },
                ],
                "assumptions": [],
                "summary": "old_summary",
            },
            "trip_constraints": {"city": "北京", "days": 2},
            "messages": [],
        },
    )

    ctx = AppContext(
        session_store=session_store,
        graph_factory=_DoneGraph,
        engine_version="v2",
        strict_required_fields=False,
        llm=None,
        cache={},
        key_manager=None,
        logger=None,
        persistence_repo=None,
    )

    result = plan_trip(
        TripRequest(
            session_id="s1",
            message="把第2天故宫换成颐和园",
            constraints={},
            metadata={
                "edit_patch": {
                    "replace_stop": {
                        "day_number": 2,
                        "old_poi": "故宫",
                        "new_poi": "颐和园",
                    }
                }
            },
        ),
        ctx,
    )

    assert result.status.value == "done"
    assert result.itinerary is not None
    day1 = result.itinerary["days"][0]["schedule"][0]["poi"]["name"]
    day2 = result.itinerary["days"][1]["schedule"][0]["poi"]["name"]
    assert day1 == "天安门"
    assert day2 == "颐和园"
    assert any(
        "edit_patch:replace_stop day=2" in row
        for row in result.itinerary.get("assumptions", [])
    )

