from __future__ import annotations

from pathlib import Path

from tools.release_summary import build_summary, render_summary_text


def test_build_summary_uses_confidence_metrics_when_available():
    release_report = {
        "passed": True,
        "metrics": {
            "unknown_fact_rate": 0.0,
            "verified_fact_ratio": 0.82,
            "l0_real_routing_ratio": 0.5,
            "routing_fixture_rate": 0.5,
            "fallback_rate": 0.0,
            "schema_valid_rate": 1.0,
            "constraint_satisfaction_rate": 1.0,
            "travel_feasibility_rate": 1.0,
            "clarifying_correctness": 1.0,
            "plan_success_rate": 1.0,
            "concurrency_isolation": 1.0,
            "p95_latency_ms": 88.5,
            "confidence_samples": 3,
            "confidence_mean": 0.66,
            "confidence_p50": 0.67,
            "confidence_p90": 0.8,
        },
        "case_rows": [],
    }
    eval_report = {
        "average_score": 0.98,
        "pass_rate": 1.0,
        "passed": 16,
        "total_cases": 16,
    }

    summary = build_summary(
        release_gate_report=release_report,
        release_gate_path=Path("eval/reports/release_gate_latest.json"),
        eval_report=eval_report,
        eval_path=Path("app/eval/reports/eval_x.json"),
    )

    assert summary["release_gate_passed"] is True
    assert summary["confidence"]["samples"] == 3
    assert summary["confidence"]["mean"] == 0.66
    assert summary["confidence"]["p50"] == 0.67
    assert summary["confidence"]["p90"] == 0.8
    assert summary["metrics"]["verified_fact_ratio"] == 0.82


def test_build_summary_computes_confidence_from_case_rows_when_metric_missing():
    release_report = {
        "passed": False,
        "metrics": {
            "unknown_fact_rate": 0.05,
            "verified_fact_ratio": 0.62,
            "l0_real_routing_ratio": 0.2,
            "routing_fixture_rate": 0.8,
            "fallback_rate": 0.1,
        },
        "case_rows": [
            {"id": "a", "confidence_score_case": 0.3},
            {"id": "b", "confidence_score_case": 0.6},
            {"id": "c", "confidence_score_case": 0.8},
        ],
    }

    summary = build_summary(
        release_gate_report=release_report,
        release_gate_path=Path("eval/reports/release_gate_latest.json"),
    )
    rendered = render_summary_text(summary)

    assert summary["confidence"]["samples"] == 3
    assert summary["confidence"]["mean"] == 0.5667
    assert summary["confidence"]["p50"] == 0.6
    assert summary["confidence"]["p90"] == 0.8
    assert "- confidence_mean: 0.5667" in rendered
