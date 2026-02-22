from __future__ import annotations

from app.observability.slo import evaluate_slo_objectives, infer_slo_profile, resolve_slo_objectives


def test_evaluate_slo_objectives_pass_case():
    snapshot = {
        "total_requests": 100,
        "success_rate": 0.995,
        "p95_latency_ms": 2200,
        "degrade_counts": {"L0": 50, "L1": 40, "L2": 10, "L3": 0},
        "tool_calls": {"poi.search": {"count": 100, "error": 1}},
    }
    objectives = [
        {"name": "availability", "metric": "success_rate", "op": ">=", "target": 0.99},
        {"name": "latency", "metric": "p95_latency_ms", "op": "<=", "target": 3000},
        {"name": "tool_errors", "metric": "tool_error_rate", "op": "<=", "target": 0.05},
        {"name": "realtime_mix", "metric": "l0_ratio", "op": ">=", "target": 0.3},
    ]
    report = evaluate_slo_objectives(snapshot, objectives)
    assert report["passed"] is True
    assert report["failed"] == []


def test_evaluate_slo_objectives_fail_case():
    snapshot = {
        "total_requests": 80,
        "success_rate": 0.90,
        "p95_latency_ms": 4500,
        "degrade_counts": {"L0": 5, "L1": 30, "L2": 20, "L3": 25},
        "tool_calls": {"poi.search": {"count": 10, "error": 3}},
    }
    objectives = [
        {"name": "availability", "metric": "success_rate", "op": ">=", "target": 0.99},
        {"name": "latency", "metric": "p95_latency_ms", "op": "<=", "target": 3000},
        {"name": "tool_errors", "metric": "tool_error_rate", "op": "<=", "target": 0.05},
        {"name": "degrade_l3", "metric": "l3_ratio", "op": "<=", "target": 0.1},
    ]
    report = evaluate_slo_objectives(snapshot, objectives)
    assert report["passed"] is False
    assert len(report["failed"]) == 4


def test_infer_slo_profile_by_l0_ratio():
    realtime_snapshot = {"total_requests": 10, "degrade_counts": {"L0": 4, "L3": 1}}
    degraded_snapshot = {"total_requests": 10, "degrade_counts": {"L0": 1, "L3": 8}}
    assert infer_slo_profile(realtime_snapshot, realtime_l0_ratio_min=0.3) == "realtime"
    assert infer_slo_profile(degraded_snapshot, realtime_l0_ratio_min=0.3) == "degraded"


def test_resolve_slo_objectives_supports_auto_profiles():
    config = {
        "auto": {"realtime_l0_ratio_min": 0.3, "default_profile": "degraded"},
        "profiles": {
            "realtime": [{"name": "a", "metric": "success_rate", "op": ">=", "target": 0.99}],
            "degraded": [{"name": "b", "metric": "success_rate", "op": ">=", "target": 0.95}],
        },
    }
    snapshot = {"total_requests": 10, "degrade_counts": {"L0": 1, "L3": 8}}
    profile, objectives = resolve_slo_objectives(
        snapshot=snapshot,
        objectives_config=config,
        profile="auto",
    )
    assert profile == "degraded"
    assert isinstance(objectives, list) and len(objectives) == 1


def test_resolve_slo_objectives_list_config_backward_compatible():
    snapshot = {"total_requests": 1}
    config = [{"name": "x", "metric": "success_rate", "op": ">=", "target": 0.9}]
    profile, objectives = resolve_slo_objectives(
        snapshot=snapshot,
        objectives_config=config,
        profile="auto",
    )
    assert profile == "custom"
    assert objectives == config
