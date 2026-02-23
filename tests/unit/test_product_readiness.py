"""Tests for product readiness report aggregation."""

from __future__ import annotations

import json
from pathlib import Path

from tools.product_readiness import build_readiness_report


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_readiness_report_all_green(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    _write(report_dir / "product_acceptance_latest.json", {"full_passed": True})
    _write(report_dir / "frontend_e2e_latest.json", {"stats": {"expected": 3, "unexpected": 0}})
    _write(
        report_dir / "loadtest_20260223_010000.json",
        {"success_rate": 1.0, "p95_latency_ms": 1200.0, "capacity_conclusion": {"meets_target": True}},
    )
    _write(report_dir / "slo_latest.json", {"passed": True, "metrics": {"success_rate": 1.0, "p95_latency_ms": 1500}})
    _write(
        report_dir / "slo_realtime_latest.json",
        {"passed": True, "metrics": {"success_rate": 1.0, "p95_latency_ms": 1800}},
    )
    _write(report_dir / "dependency_fault_drill_latest.json", {"passed": True})
    _write(report_dir / "persistence_drill_latest.json", {"passed": True})
    _write(
        report_dir / "observability_stack_latest.json",
        {"prometheus_ready": True, "backend_target_healthy": True, "grafana_ok": True, "alert_rule_count": 3},
    )
    _write(report_dir / "ci_remote_latest.json", {"latest_all_green": True, "latest_run_id": 1, "latest_run_conclusion": "success"})

    report = build_readiness_report(report_dir)

    assert report["overall_passed"] is True
    assert len(report["checks"]) == 9


def test_build_readiness_report_fails_without_passing_loadtest(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    _write(report_dir / "product_acceptance_latest.json", {"full_passed": True})
    _write(report_dir / "frontend_e2e_latest.json", {"stats": {"expected": 3, "unexpected": 0}})
    _write(
        report_dir / "loadtest_20260223_010000.json",
        {"success_rate": 0.5, "p95_latency_ms": 9000.0, "capacity_conclusion": {"meets_target": False}},
    )
    _write(report_dir / "slo_latest.json", {"passed": True, "metrics": {"success_rate": 1.0, "p95_latency_ms": 1500}})
    _write(
        report_dir / "slo_realtime_latest.json",
        {"passed": True, "metrics": {"success_rate": 1.0, "p95_latency_ms": 1800}},
    )
    _write(report_dir / "dependency_fault_drill_latest.json", {"passed": True})
    _write(report_dir / "persistence_drill_latest.json", {"passed": True})
    _write(
        report_dir / "observability_stack_latest.json",
        {"prometheus_ready": True, "backend_target_healthy": True, "grafana_ok": True, "alert_rule_count": 3},
    )
    _write(report_dir / "ci_remote_latest.json", {"latest_all_green": True, "latest_run_id": 1, "latest_run_conclusion": "success"})

    report = build_readiness_report(report_dir)

    assert report["overall_passed"] is False
    capacity = [row for row in report["checks"] if row["name"] == "capacity_500_concurrency"][0]
    assert capacity["passed"] is False
