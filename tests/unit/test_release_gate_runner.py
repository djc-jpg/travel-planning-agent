"""Release gate hard-threshold tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import eval.release_gate_runner as gate


class _Status:
    def __init__(self, value: str) -> None:
        self.value = value


class _Result:
    def __init__(self, *, status: str, itinerary: dict, degrade_level: str) -> None:
        self.status = _Status(status)
        self.itinerary = itinerary
        self.degrade_level = degrade_level
        self.request_id = "r1"
        self.trace_id = "t1"


def _fixture_itinerary(*, routing_source: str, verified_fact_ratio: float, fallback_count: int) -> dict:
    return {
        "city": "x",
        "days": [
            {
                "day_number": 1,
                "schedule": [
                    {
                        "poi": {
                            "id": "p1",
                            "name": "p1",
                            "city": "x",
                            "ticket_price": 10.0,
                            "open_time": "09:00-17:00",
                            "closed_rules": "none",
                        },
                        "start_time": "09:00",
                        "end_time": "10:30",
                        "travel_minutes": 0.0,
                        "buffer_minutes": 10.0,
                        "is_backup": False,
                        "notes": "",
                    }
                ],
                "meal_windows": ["12:00-13:00"],
            }
        ],
        "unknown_fields": [],
        "degrade_level": "L1",
        "routing_source": routing_source,
        "verified_fact_ratio": verified_fact_ratio,
        "fallback_count": fallback_count,
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_release_gate_fails_when_l0_ratio_is_insufficient(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "release_gate.json"
    cases_path = tmp_path / "cases.json"

    _write_json(
        config_path,
        {
            "schema_valid_rate": ">=1.0",
            "clarifying_correctness": ">=1.0",
            "constraint_satisfaction_rate": ">=1.0",
            "travel_feasibility_rate": ">=1.0",
            "plan_success_rate": ">=1.0",
            "unknown_fact_rate": "<=1.0",
            "l0_real_routing_ratio": ">=0.30",
            "fallback_rate": "<=1.0",
            "verified_fact_ratio": ">=0.0",
            "routing_fixture_rate": "<=1.0",
            "concurrency_isolation": "==1.00",
            "p95_latency_ms": "<999999",
        },
    )
    _write_json(
        cases_path,
        [
            {
                "id": "c1",
                "user_request": "x",
                "constraints": {"city": "x", "days": 1},
                "context": {},
                "expected_properties": {"status": "done"},
            },
            {
                "id": "c2",
                "user_request": "x",
                "constraints": {"city": "x", "days": 1},
                "context": {},
                "expected_properties": {"status": "done"},
            },
        ],
    )

    def _fake_plan_trip(_request, _ctx):
        return _Result(
            status="done",
            itinerary=_fixture_itinerary(
                routing_source="fixture",
                verified_fact_ratio=0.95,
                fallback_count=0,
            ),
            degrade_level="L1",
        )

    monkeypatch.setattr(gate, "plan_trip", _fake_plan_trip)
    monkeypatch.setattr(gate, "make_app_context", lambda: object())
    monkeypatch.setattr(
        gate,
        "_concurrency_50",
        lambda _ctx, requests=50: {
            "requests": requests,
            "score": 1.0,
            "success_rate": 1.0,
            "details": ["ok"],
        },
    )
    monkeypatch.setattr(
        gate,
        "_run_degrade_eval_cases",
        lambda path=gate._DEFAULT_DEGRADE_CASES: {
            "coverage": {"L0": True, "L1": True, "L2": True, "L3": True},
            "rows": [],
        },
    )
    monkeypatch.setattr(
        gate,
        "_run_edit_roundtrip_probe",
        lambda: {"passed": True, "checks": {}, "details": ["ok"]},
    )
    monkeypatch.setattr(gate, "_REPORT_DIR", tmp_path / "reports")

    report = gate.run_release_gate(config_path=config_path, cases_path=cases_path)

    assert report["passed"] is False
    assert report["metrics"]["l0_real_routing_ratio"] == 0.0
    assert any(row.get("metric") == "l0_real_routing_ratio" for row in report["failures"])


def test_release_gate_fails_when_infrastructure_poi_leaks(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "release_gate.json"
    cases_path = tmp_path / "cases.json"

    _write_json(
        config_path,
        {
            "schema_valid_rate": ">=1.0",
            "clarifying_correctness": ">=1.0",
            "constraint_satisfaction_rate": ">=1.0",
            "travel_feasibility_rate": ">=1.0",
            "plan_success_rate": ">=1.0",
            "unknown_fact_rate": "<=1.0",
            "l0_real_routing_ratio": ">=0.0",
            "fallback_rate": "<=1.0",
            "verified_fact_ratio": ">=0.0",
            "routing_fixture_rate": "<=1.0",
            "infrastructure_poi_rate": "==0.0",
            "business_poi_leak_rate": "==1.0",
            "food_night_coverage_rate": ">=0.0",
            "avoid_constraint_pass_rate": ">=0.0",
            "concurrency_isolation": "==1.00",
            "p95_latency_ms": "<999999",
        },
    )
    _write_json(
        cases_path,
        [
            {
                "id": "c_food",
                "user_request": "food and night",
                "constraints": {"city": "x", "days": 1},
                "context": {},
                "expected_properties": {"status": "done"},
                "routing_provider": "real",
            }
        ],
    )

    def _fake_plan_trip(_request, _ctx):
        itinerary = _fixture_itinerary(
            routing_source="real",
            verified_fact_ratio=0.95,
            fallback_count=0,
        )
        itinerary["degrade_level"] = "L0"
        itinerary["days"][0]["schedule"][0]["poi"]["name"] = "city parking lot"
        return _Result(status="done", itinerary=itinerary, degrade_level="L0")

    monkeypatch.setattr(gate, "plan_trip", _fake_plan_trip)
    monkeypatch.setattr(gate, "make_app_context", lambda: object())
    monkeypatch.setattr(
        gate,
        "_concurrency_50",
        lambda _ctx, requests=50: {
            "requests": requests,
            "score": 1.0,
            "success_rate": 1.0,
            "details": ["ok"],
        },
    )
    monkeypatch.setattr(
        gate,
        "_run_degrade_eval_cases",
        lambda path=gate._DEFAULT_DEGRADE_CASES: {
            "coverage": {"L0": True, "L1": True, "L2": True, "L3": True},
            "rows": [],
        },
    )
    monkeypatch.setattr(
        gate,
        "_run_edit_roundtrip_probe",
        lambda: {"passed": True, "checks": {}, "details": ["ok"]},
    )
    monkeypatch.setattr(gate, "_REPORT_DIR", tmp_path / "reports")

    report = gate.run_release_gate(config_path=config_path, cases_path=cases_path)

    assert report["passed"] is False
    assert report["metrics"]["infrastructure_poi_rate"] > 0.0
    assert any(row.get("metric") == "infrastructure_poi_rate" for row in report["failures"])


def test_infrastructure_keyword_detector_catches_pickup_dropoff_variants():
    item = SimpleNamespace(
        poi=SimpleNamespace(
            name="博物馆南门接驳上客点",
            semantic_type="unknown",
        )
    )
    assert gate._is_infrastructure_stop(item) is True


def test_release_gate_fails_when_business_poi_leaks(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "release_gate.json"
    cases_path = tmp_path / "cases.json"

    _write_json(
        config_path,
        {
            "schema_valid_rate": ">=1.0",
            "clarifying_correctness": ">=1.0",
            "constraint_satisfaction_rate": ">=1.0",
            "travel_feasibility_rate": ">=1.0",
            "plan_success_rate": ">=1.0",
            "unknown_fact_rate": "<=1.0",
            "l0_real_routing_ratio": ">=0.0",
            "fallback_rate": "<=1.0",
            "verified_fact_ratio": ">=0.0",
            "routing_fixture_rate": "<=1.0",
            "infrastructure_poi_rate": "==1.0",
            "business_poi_leak_rate": "==0.0",
            "food_night_coverage_rate": ">=0.0",
            "avoid_constraint_pass_rate": ">=0.0",
            "concurrency_isolation": "==1.00",
            "p95_latency_ms": "<999999",
        },
    )
    _write_json(
        cases_path,
        [
            {
                "id": "c_business",
                "user_request": "x",
                "constraints": {"city": "x", "days": 1},
                "context": {},
                "expected_properties": {"status": "done"},
                "routing_provider": "real",
            }
        ],
    )

    def _fake_plan_trip(_request, _ctx):
        itinerary = _fixture_itinerary(
            routing_source="real",
            verified_fact_ratio=0.95,
            fallback_count=0,
        )
        itinerary["degrade_level"] = "L0"
        itinerary["days"][0]["schedule"][0]["poi"]["name"] = "中国联通营业厅(示例点)"
        return _Result(status="done", itinerary=itinerary, degrade_level="L0")

    monkeypatch.setattr(gate, "plan_trip", _fake_plan_trip)
    monkeypatch.setattr(gate, "make_app_context", lambda: object())
    monkeypatch.setattr(
        gate,
        "_concurrency_50",
        lambda _ctx, requests=50: {
            "requests": requests,
            "score": 1.0,
            "success_rate": 1.0,
            "details": ["ok"],
        },
    )
    monkeypatch.setattr(
        gate,
        "_run_degrade_eval_cases",
        lambda path=gate._DEFAULT_DEGRADE_CASES: {
            "coverage": {"L0": True, "L1": True, "L2": True, "L3": True},
            "rows": [],
        },
    )
    monkeypatch.setattr(
        gate,
        "_run_edit_roundtrip_probe",
        lambda: {"passed": True, "checks": {}, "details": ["ok"]},
    )
    monkeypatch.setattr(gate, "_REPORT_DIR", tmp_path / "reports")

    report = gate.run_release_gate(config_path=config_path, cases_path=cases_path)

    assert report["passed"] is False
    assert report["metrics"]["business_poi_leak_rate"] > 0.0
    assert any(row.get("metric") == "business_poi_leak_rate" for row in report["failures"])


def test_business_keyword_detector_catches_business_hall():
    item = SimpleNamespace(
        poi=SimpleNamespace(
            name="中国联通营业厅",
            semantic_type="unknown",
        )
    )
    assert gate._is_non_experience_business_stop(item) is True


def test_release_gate_fails_when_edit_roundtrip_probe_fails(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "release_gate.json"
    cases_path = tmp_path / "cases.json"

    _write_json(
        config_path,
        {
            "schema_valid_rate": ">=1.0",
            "clarifying_correctness": ">=1.0",
            "constraint_satisfaction_rate": ">=1.0",
            "travel_feasibility_rate": ">=1.0",
            "plan_success_rate": ">=1.0",
            "unknown_fact_rate": "<=1.0",
            "l0_real_routing_ratio": ">=0.0",
            "fallback_rate": "<=1.0",
            "verified_fact_ratio": ">=0.0",
            "routing_fixture_rate": "<=1.0",
            "infrastructure_poi_rate": "==0.0",
            "food_night_coverage_rate": ">=0.0",
            "avoid_constraint_pass_rate": ">=0.0",
            "concurrency_isolation": "==1.00",
            "p95_latency_ms": "<999999",
        },
    )
    _write_json(
        cases_path,
        [
            {
                "id": "c1",
                "user_request": "x",
                "constraints": {"city": "x", "days": 1},
                "context": {},
                "expected_properties": {"status": "done"},
                "routing_provider": "real",
            }
        ],
    )

    def _fake_plan_trip(_request, _ctx):
        itinerary = _fixture_itinerary(
            routing_source="real",
            verified_fact_ratio=0.95,
            fallback_count=0,
        )
        itinerary["degrade_level"] = "L0"
        return _Result(status="done", itinerary=itinerary, degrade_level="L0")

    monkeypatch.setattr(gate, "plan_trip", _fake_plan_trip)
    monkeypatch.setattr(gate, "make_app_context", lambda: object())
    monkeypatch.setattr(
        gate,
        "_concurrency_50",
        lambda _ctx, requests=50: {
            "requests": requests,
            "score": 1.0,
            "success_rate": 1.0,
            "details": ["ok"],
        },
    )
    monkeypatch.setattr(
        gate,
        "_run_degrade_eval_cases",
        lambda path=gate._DEFAULT_DEGRADE_CASES: {
            "coverage": {"L0": True, "L1": True, "L2": True, "L3": True},
            "rows": [],
        },
    )
    monkeypatch.setattr(
        gate,
        "_run_edit_roundtrip_probe",
        lambda: {"passed": False, "checks": {"history_contains_both": False}, "details": ["history_contains_both"]},
    )
    monkeypatch.setattr(gate, "_REPORT_DIR", tmp_path / "reports")

    report = gate.run_release_gate(config_path=config_path, cases_path=cases_path)

    assert report["passed"] is False
    assert report["metrics"]["edit_roundtrip_pass_rate"] == 0.0
    assert any(row.get("metric") == "edit_roundtrip_pass_rate" for row in report["failures"])
