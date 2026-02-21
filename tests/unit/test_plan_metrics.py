"""Plan metrics tests."""

from __future__ import annotations

from app.application.context import AppContext
from app.application.contracts import TripRequest
from app.application.plan_trip import plan_trip
from app.observability.plan_metrics import get_plan_metrics, observe_tool_call


class _SessionStore:
    backend = "test"

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    def get(self, session_id: str):
        return self._data.get(session_id)

    def save(self, session_id: str, state: dict) -> None:
        self._data[session_id] = state

    @property
    def active_count(self) -> int:
        return len(self._data)


class _NeverCalledGraph:
    def invoke(self, _state: dict) -> dict:
        raise AssertionError("graph.invoke should not run when strict clarifying gate triggers")


class _DoneGraph:
    def invoke(self, state: dict) -> dict:
        next_state = dict(state)
        next_state["status"] = "done"
        next_state["final_itinerary"] = {"city": "杭州", "days": [{"day_number": 1}, {"day_number": 2}]}
        next_state.setdefault("messages", [])
        next_state["messages"].append({"role": "assistant", "content": "ok"})
        return next_state


def test_plan_metrics_records_clarifying_and_done():
    metrics = get_plan_metrics()
    metrics.reset()

    clarifying_ctx = AppContext(
        session_store=_SessionStore(),
        graph_factory=_NeverCalledGraph,
        engine_version="v2",
        strict_required_fields=True,
        llm=None,
        cache={},
        key_manager=None,
        logger=None,
    )
    done_ctx = AppContext(
        session_store=_SessionStore(),
        graph_factory=_DoneGraph,
        engine_version="v2",
        strict_required_fields=False,
        llm=None,
        cache={},
        key_manager=None,
        logger=None,
    )

    clarifying_result = plan_trip(TripRequest(message="帮我规划旅行"), clarifying_ctx)
    done_result = plan_trip(
        TripRequest(
            message="去杭州2天，2026-04-01到2026-04-02",
            constraints={"city": "杭州", "days": 2, "date_start": "2026-04-01", "date_end": "2026-04-02"},
        ),
        done_ctx,
    )

    assert clarifying_result.status.value == "clarifying"
    assert done_result.status.value == "done"

    snap = metrics.snapshot()
    assert snap["total_requests"] == 2
    assert snap["status_counts"]["clarifying"] >= 1
    assert snap["status_counts"]["done"] >= 1
    assert snap["engine_counts"]["v2"] == 2
    assert snap["latency"]["count"] == 2

    observe_tool_call(tool_name="poi.search", latency_ms=12.5, ok=True, returned_count=8)
    observe_tool_call(
        tool_name="poi.search",
        latency_ms=21.0,
        ok=False,
        error_code="TimeoutError",
        returned_count=0,
    )
    tool_snap = metrics.snapshot()["tool_calls"]["poi.search"]
    assert tool_snap["count"] == 2
    assert tool_snap["ok"] == 1
    assert tool_snap["error"] == 1
    assert tool_snap["error_codes"]["TimeoutError"] == 1
