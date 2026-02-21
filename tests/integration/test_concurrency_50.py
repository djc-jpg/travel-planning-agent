"""50-request concurrency isolation pressure test."""

from __future__ import annotations

import copy
import threading
from concurrent.futures import ThreadPoolExecutor

from app.application.context import AppContext
from app.application.contracts import TripRequest
from app.application.plan_trip import plan_trip


class _Store:
    backend = "memory-test"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: dict[str, dict] = {}

    def get(self, session_id: str):
        with self._lock:
            row = self._rows.get(session_id)
            return copy.deepcopy(row) if row is not None else None

    def save(self, session_id: str, state: dict) -> None:
        with self._lock:
            self._rows[session_id] = copy.deepcopy(state)

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._rows)


class _EchoGraph:
    def invoke(self, state: dict) -> dict:
        next_state = copy.deepcopy(state)
        constraints = dict(next_state.get("trip_constraints", {}))
        session_id = str(next_state.get("session_id", ""))
        cache_key = str(constraints.get("cache_key", ""))

        next_state["status"] = "done"
        next_state["final_itinerary"] = {
            "city": constraints.get("city", "杭州"),
            "days": [{"day_number": 1}, {"day_number": 2}],
            "session_id": session_id,
            "cache_key": cache_key,
        }
        next_state.setdefault("messages", [])
        next_state["messages"].append({"role": "assistant", "content": f"ok:{cache_key}"})
        return next_state


def test_concurrency_50_isolation_and_success_rate():
    ctx = AppContext(
        session_store=_Store(),
        graph_factory=_EchoGraph,
        engine_version="v2",
        strict_required_fields=False,
        llm=object(),
        cache={"poi": {}, "route": {}, "weather": {}},
        key_manager=object(),
        logger=object(),
    )

    def _run_case(i: int):
        session_id = f"stress_{i:03d}"
        cache_key = f"cache_{i:03d}"
        result = plan_trip(
            TripRequest(
                message=f"杭州2天，2026-04-01到2026-04-02，并发{i}",
                session_id=session_id,
                constraints={
                    "city": "杭州",
                    "days": 2,
                    "date_start": "2026-04-01",
                    "date_end": "2026-04-02",
                    "cache_key": cache_key,
                },
            ),
            ctx,
        ).model_dump(mode="json")
        return session_id, cache_key, result

    with ThreadPoolExecutor(max_workers=50) as pool:
        rows = list(pool.map(_run_case, range(50)))

    success = 0
    for session_id, cache_key, result in rows:
        if result["status"] in {"done", "clarifying"}:
            success += 1
        assert result["session_id"] == session_id
        itinerary = result.get("itinerary") or {}
        assert itinerary.get("session_id") == session_id
        assert itinerary.get("cache_key") == cache_key

    success_rate = success / 50
    assert success_rate >= 0.99

