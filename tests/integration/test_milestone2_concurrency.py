"""Milestone-2 isolation tests: fake context + concurrent plan requests."""

from __future__ import annotations

import copy
import threading
from concurrent.futures import ThreadPoolExecutor

from app.application.context import AppContext
from app.application.contracts import TripRequest
from app.application.plan_trip import plan_trip


class FakeSessionStore:
    backend = "fake-memory"

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            state = self._data.get(session_id)
            return copy.deepcopy(state) if state is not None else None

    def save(self, session_id: str, state: dict) -> None:
        with self._lock:
            self._data[session_id] = copy.deepcopy(state)

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._data)

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            return copy.deepcopy(self._data)


class _NeverCalledGraph:
    def invoke(self, _state: dict) -> dict:
        raise AssertionError("graph.invoke should not be called in strict clarifying gate")


class _ConcurrentEchoGraph:
    def invoke(self, state: dict) -> dict:
        next_state = copy.deepcopy(state)
        constraints = dict(next_state.get("trip_constraints", {}))
        cache_key = str(constraints.get("cache_key", ""))
        session_id = str(next_state.get("session_id", ""))

        next_state["status"] = "done"
        next_state["final_itinerary"] = {
            "city": constraints.get("city", "杭州"),
            "days": [{"day_number": 1}, {"day_number": 2}],
            "cache_key": cache_key,
            "session_id": session_id,
        }
        next_state.setdefault("messages", [])
        next_state["messages"].append({"role": "assistant", "content": f"ok:{cache_key}"})
        return next_state


def test_fake_context_can_drive_plan_trip_without_singletons():
    ctx = AppContext(
        session_store=FakeSessionStore(),
        graph_factory=_NeverCalledGraph,
        engine_version="v2",
        strict_required_fields=True,
        llm=object(),
        cache={"poi": {}, "route": {}, "weather": {}},
        key_manager=object(),
        logger=object(),
    )

    result = plan_trip(TripRequest(message="帮我规划一个行程"), ctx)

    assert result.status.value == "clarifying"
    assert result.next_questions


def test_concurrent_plan_requests_are_isolated():
    store = FakeSessionStore()
    ctx = AppContext(
        session_store=store,
        graph_factory=_ConcurrentEchoGraph,
        engine_version="v2",
        strict_required_fields=False,
        llm=object(),
        cache={"poi": {}, "route": {}, "weather": {}},
        key_manager=object(),
        logger=object(),
    )

    def _run_case(i: int) -> tuple[str, str, dict]:
        session_id = f"sess_{i:02d}"
        cache_key = f"cache_{i:02d}"
        req = TripRequest(
            message=f"我想去杭州玩2天，2026-04-01到2026-04-02，request={i}",
            session_id=session_id,
            constraints={
                "city": "杭州",
                "days": 2,
                "date_start": "2026-04-01",
                "date_end": "2026-04-02",
                "cache_key": cache_key,
            },
        )
        result = plan_trip(req, ctx).model_dump(mode="json")
        return session_id, cache_key, result

    with ThreadPoolExecutor(max_workers=20) as pool:
        rows = list(pool.map(_run_case, range(20)))

    assert len(rows) == 20
    expected_cache_by_session = {session_id: cache_key for session_id, cache_key, _ in rows}

    returned_sessions = set()
    returned_cache_keys = set()
    for session_id, cache_key, result in rows:
        returned_sessions.add(result["session_id"])
        returned_cache_keys.add(result["itinerary"]["cache_key"])
        assert result["status"] == "done"
        assert result["session_id"] == session_id
        assert result["itinerary"]["session_id"] == session_id
        assert result["itinerary"]["cache_key"] == cache_key

    assert returned_sessions == set(expected_cache_by_session.keys())
    assert len(returned_cache_keys) == 20

    snapshot = store.snapshot()
    assert set(snapshot.keys()) == set(expected_cache_by_session.keys())
    for session_id, expected_cache_key in expected_cache_by_session.items():
        state = snapshot[session_id]
        assert state.get("session_id") == session_id
        assert state.get("trip_constraints", {}).get("cache_key") == expected_cache_key
        assert len([msg for msg in state.get("messages", []) if msg.get("role") == "user"]) == 1

