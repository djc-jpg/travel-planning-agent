"""SQLite persistence repository and plan_trip integration tests."""

from __future__ import annotations

import json
import sqlite3

from app.application.context import AppContext
from app.application.contracts import TripRequest
from app.application.plan_trip import plan_trip
from app.persistence.models import ArtifactRecord, PlanRecord, RequestRecord, SessionRecord
from app.persistence.sqlite_repository import SQLitePlanPersistenceRepository


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
                            "notes": "routing_confidence=0.72",
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


def test_sqlite_repository_roundtrip(tmp_path):
    repo = SQLitePlanPersistenceRepository(tmp_path / "trip_agent.sqlite3")
    now = "2026-02-21T00:00:00Z"

    repo.save_session(SessionRecord(session_id="s1", updated_at=now, status="done", trace_id="t1"))
    repo.save_request(
        RequestRecord(
            request_id="r1",
            session_id="s1",
            trace_id="t1",
            message="go",
            constraints={"city": "杭州"},
            user_profile={"themes": ["history"]},
            metadata={"m": 1},
            created_at=now,
        )
    )
    repo.save_plan(
        PlanRecord(
            request_id="r1",
            session_id="s1",
            trace_id="t1",
            status="done",
            degrade_level="L1",
            confidence_score=0.7,
            run_fingerprint={"run_mode": "DEGRADED"},
            itinerary={"city": "杭州", "days": []},
            issues=[],
            next_questions=[],
            field_evidence={},
            metrics={"unknown_ratio": 0.0},
            created_at=now,
        )
    )
    repo.save_artifact(
        ArtifactRecord(
            request_id="r1",
            artifact_type="itinerary",
            payload={"city": "杭州"},
            created_at=now,
        )
    )

    with sqlite3.connect(tmp_path / "trip_agent.sqlite3") as conn:
        sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        requests = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        plans = conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
        artifacts = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        run_fp_json = conn.execute("SELECT run_fingerprint_json FROM plans WHERE request_id='r1'").fetchone()[0]

    assert sessions == 1
    assert requests == 1
    assert plans == 1
    assert artifacts == 1
    assert json.loads(run_fp_json)["run_mode"] == "DEGRADED"


def test_sqlite_repository_query_history_and_export(tmp_path):
    repo = SQLitePlanPersistenceRepository(tmp_path / "trip_agent.sqlite3")
    now = "2026-02-21T00:00:00Z"

    repo.save_session(SessionRecord(session_id="s1", updated_at=now, status="done", trace_id="t1"))
    repo.save_request(
        RequestRecord(
            request_id="r1",
            session_id="s1",
            trace_id="t1",
            message="go beijing",
            constraints={"city": "beijing"},
            user_profile={"themes": ["history"]},
            metadata={"edit_mode": "diff"},
            created_at=now,
        )
    )
    repo.save_plan(
        PlanRecord(
            request_id="r1",
            session_id="s1",
            trace_id="t1",
            status="done",
            degrade_level="L1",
            confidence_score=0.82,
            run_fingerprint={"run_mode": "DEGRADED", "trace_id": "t1"},
            itinerary={"city": "beijing", "days": []},
            issues=[],
            next_questions=[],
            field_evidence={},
            metrics={"verified_fact_ratio": 0.8},
            created_at=now,
        )
    )
    repo.save_artifact(
        ArtifactRecord(
            request_id="r1",
            artifact_type="edit_patch",
            payload={"op": "replace_stop", "day": 2},
            created_at=now,
        )
    )

    history = repo.list_session_history("s1", limit=5)
    assert len(history) == 1
    assert history[0].request_id == "r1"
    assert history[0].status == "done"
    assert history[0].run_fingerprint["run_mode"] == "DEGRADED"

    export = repo.get_plan_export("r1")
    assert export is not None
    assert export.message == "go beijing"
    assert export.metrics["verified_fact_ratio"] == 0.8
    assert len(export.artifacts) == 1
    assert export.artifacts[0].artifact_type == "edit_patch"


def test_sqlite_repository_list_sessions_ordering_and_limit(tmp_path):
    repo = SQLitePlanPersistenceRepository(tmp_path / "trip_agent.sqlite3")
    repo.save_session(
        SessionRecord(
            session_id="chat_old",
            updated_at="2026-02-21T00:00:00Z",
            status="done",
            trace_id="trace_old",
        )
    )
    repo.save_session(
        SessionRecord(
            session_id="chat_new",
            updated_at="2026-02-21T02:00:00Z",
            status="pending",
            trace_id="trace_new",
        )
    )

    sessions = repo.list_sessions(limit=1)
    assert len(sessions) == 1
    assert sessions[0].session_id == "chat_new"
    assert sessions[0].last_status == "pending"
    assert sessions[0].last_trace_id == "trace_new"


def test_plan_trip_persists_run_records(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUTING_PROVIDER", "fixture")
    repo = SQLitePlanPersistenceRepository(tmp_path / "trip_agent.sqlite3")
    ctx = AppContext(
        session_store=_SessionStore(),
        graph_factory=_DoneGraph,
        engine_version="v2",
        strict_required_fields=False,
        llm=None,
        cache={},
        key_manager=None,
        logger=None,
        persistence_repo=repo,
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
    assert result.request_id
    assert result.trace_id
    assert result.run_fingerprint is not None

    with sqlite3.connect(tmp_path / "trip_agent.sqlite3") as conn:
        req_row = conn.execute(
            "SELECT request_id, session_id, trace_id FROM requests WHERE request_id=?",
            (result.request_id,),
        ).fetchone()
        plan_row = conn.execute(
            "SELECT run_fingerprint_json, metrics_json FROM plans WHERE request_id=?",
            (result.request_id,),
        ).fetchone()
        artifact_count = conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE request_id=?",
            (result.request_id,),
        ).fetchone()[0]

    assert req_row is not None
    assert req_row[0] == result.request_id
    assert req_row[2] == result.trace_id
    assert plan_row is not None
    assert json.loads(plan_row[0])["trace_id"] == result.trace_id
    assert "unknown_ratio" in json.loads(plan_row[1])
    assert artifact_count == 1


def test_plan_trip_roundtrip_generate_edit_history_export(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUTING_PROVIDER", "fixture")
    repo = SQLitePlanPersistenceRepository(tmp_path / "trip_agent.sqlite3")
    ctx = AppContext(
        session_store=_SessionStore(),
        graph_factory=_DoneGraph,
        engine_version="v2",
        strict_required_fields=False,
        llm=None,
        cache={},
        key_manager=None,
        logger=None,
        persistence_repo=repo,
    )

    session_id = "chat_flow_1"
    first = plan_trip(
        TripRequest(
            session_id=session_id,
            message="plan a one day hangzhou itinerary",
            constraints={"city": "hangzhou", "days": 1},
        ),
        ctx,
    )
    assert first.status.value == "done"
    assert first.request_id

    second = plan_trip(
        TripRequest(
            session_id=session_id,
            message="replace stop for day 1",
            constraints={"city": "hangzhou", "days": 1},
            metadata={
                "edit_patch": {
                    "replace_stop": {
                        "day_number": 1,
                        "old_poi": "old_stop",
                        "new_poi": "new_stop",
                    }
                }
            },
        ),
        ctx,
    )
    assert second.status.value == "done"
    assert second.request_id and second.request_id != first.request_id

    history = repo.list_session_history(session_id, limit=10)
    assert len(history) == 2
    history_request_ids = {item.request_id for item in history}
    assert history_request_ids == {first.request_id, second.request_id}

    export = repo.get_plan_export(second.request_id)
    assert export is not None
    assert export.session_id == session_id
    assert export.request_id == second.request_id
    assert "new_stop" in export.constraints.get("must_visit", [])
    assert "old_stop" in export.constraints.get("avoid", [])

    artifact_types = [row.artifact_type for row in export.artifacts]
    assert "itinerary" in artifact_types
    assert "edit_patch" in artifact_types


def test_sqlite_repository_history_tie_breaker_uses_latest_insert(tmp_path):
    repo = SQLitePlanPersistenceRepository(tmp_path / "trip_agent.sqlite3")
    now = "2026-02-21T10:00:00Z"
    session_id = "chat_tie_breaker"

    repo.save_session(
        SessionRecord(
            session_id=session_id,
            updated_at=now,
            status="done",
            trace_id="trace-1",
        )
    )

    repo.save_request(
        RequestRecord(
            request_id="req-1",
            session_id=session_id,
            trace_id="trace-1",
            message="first",
            constraints={"city": "hangzhou"},
            user_profile={},
            metadata={},
            created_at=now,
        )
    )
    repo.save_plan(
        PlanRecord(
            request_id="req-1",
            session_id=session_id,
            trace_id="trace-1",
            status="done",
            degrade_level="L1",
            confidence_score=0.8,
            run_fingerprint={"run_mode": "DEGRADED"},
            itinerary={},
            issues=[],
            next_questions=[],
            field_evidence={},
            metrics={},
            created_at=now,
        )
    )

    repo.save_request(
        RequestRecord(
            request_id="req-2",
            session_id=session_id,
            trace_id="trace-2",
            message="second",
            constraints={"city": "hangzhou"},
            user_profile={},
            metadata={},
            created_at=now,
        )
    )
    repo.save_plan(
        PlanRecord(
            request_id="req-2",
            session_id=session_id,
            trace_id="trace-2",
            status="done",
            degrade_level="L1",
            confidence_score=0.82,
            run_fingerprint={"run_mode": "DEGRADED"},
            itinerary={},
            issues=[],
            next_questions=[],
            field_evidence={},
            metrics={},
            created_at=now,
        )
    )

    history = repo.list_session_history(session_id, limit=10)
    assert [item.request_id for item in history] == ["req-2", "req-1"]
