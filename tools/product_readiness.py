"""Aggregate product-grade evidence reports into one readiness verdict."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_REPORT_DIR = Path("eval") / "reports"
_DEFAULT_OUTPUT_JSON = _DEFAULT_REPORT_DIR / "product_readiness_latest.json"
_DEFAULT_OUTPUT_MD = _DEFAULT_REPORT_DIR / "product_readiness_latest.md"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _latest_loadtest(report_dir: Path) -> tuple[Path | None, dict[str, Any] | None]:
    candidates = sorted(report_dir.glob("loadtest_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            payload = _read_json(path)
        except Exception:
            continue
        capacity = payload.get("capacity_conclusion", {})
        if isinstance(capacity, dict) and bool(capacity.get("meets_target")):
            return path, payload
    return None, None


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str
    report: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "report": self.report,
        }


def _check_product_acceptance(report_dir: Path) -> CheckResult:
    path = report_dir / "product_acceptance_latest.json"
    payload = _read_json(path)
    passed = bool(payload.get("full_passed"))
    detail = f"full_passed={passed}"
    return CheckResult("full_acceptance", passed, detail, str(path))


def _check_frontend_e2e(report_dir: Path) -> CheckResult:
    path = report_dir / "frontend_e2e_latest.json"
    payload = _read_json(path)
    stats = payload.get("stats", {})
    expected = int(stats.get("expected", 0)) if isinstance(stats, dict) else 0
    unexpected = int(stats.get("unexpected", 0)) if isinstance(stats, dict) else 0
    passed = expected >= 1 and unexpected == 0
    detail = f"expected={expected}, unexpected={unexpected}"
    return CheckResult("frontend_e2e", passed, detail, str(path))


def _check_loadtest(report_dir: Path) -> CheckResult:
    path, payload = _latest_loadtest(report_dir)
    if path is None or payload is None:
        return CheckResult(
            "capacity_500_concurrency",
            False,
            "no passing loadtest_*.json found",
            "",
        )
    capacity = payload.get("capacity_conclusion", {})
    passed = bool(capacity.get("meets_target")) if isinstance(capacity, dict) else False
    success_rate = float(payload.get("success_rate", 0.0))
    p95_ms = float(payload.get("p95_latency_ms", 0.0))
    detail = f"success_rate={success_rate:.4f}, p95_latency_ms={p95_ms:.2f}"
    return CheckResult("capacity_500_concurrency", passed, detail, str(path))


def _check_slo(report_dir: Path, *, file_name: str, check_name: str) -> CheckResult:
    path = report_dir / file_name
    payload = _read_json(path)
    passed = bool(payload.get("passed"))
    metrics = payload.get("metrics", {})
    if isinstance(metrics, dict):
        p95_ms = float(metrics.get("p95_latency_ms", 0.0))
        success_rate = float(metrics.get("success_rate", 0.0))
        detail = f"success_rate={success_rate:.4f}, p95_latency_ms={p95_ms:.2f}"
    else:
        detail = f"passed={passed}"
    return CheckResult(check_name, passed, detail, str(path))


def _check_simple_bool(report_dir: Path, *, file_name: str, check_name: str) -> CheckResult:
    path = report_dir / file_name
    payload = _read_json(path)
    passed = bool(payload.get("passed"))
    detail = f"passed={passed}"
    return CheckResult(check_name, passed, detail, str(path))


def _check_observability_stack(report_dir: Path) -> CheckResult:
    path = report_dir / "observability_stack_latest.json"
    payload = _read_json(path)
    prom_ready = bool(payload.get("prometheus_ready"))
    backend_ok = bool(payload.get("backend_target_healthy"))
    grafana_ok = bool(payload.get("grafana_ok"))
    rule_count = int(payload.get("alert_rule_count", 0))
    passed = prom_ready and backend_ok and grafana_ok and rule_count >= 1
    detail = (
        f"prometheus_ready={prom_ready}, backend_target_healthy={backend_ok}, "
        f"grafana_ok={grafana_ok}, alert_rule_count={rule_count}"
    )
    return CheckResult("observability_stack", passed, detail, str(path))


def _check_remote_ci(report_dir: Path) -> CheckResult:
    path = report_dir / "ci_remote_latest.json"
    payload = _read_json(path)
    passed = bool(payload.get("latest_all_green"))
    run_id = payload.get("latest_run_id")
    conclusion = payload.get("latest_run_conclusion")
    detail = f"latest_run_id={run_id}, latest_run_conclusion={conclusion}"
    return CheckResult("remote_ci_green", passed, detail, str(path))


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Product Readiness Report",
        "",
        f"- generated_at: `{report.get('generated_at')}`",
        f"- overall_passed: `{report.get('overall_passed')}`",
        "",
        "## Checks",
        "",
        "| check | passed | detail | report |",
        "| --- | --- | --- | --- |",
    ]
    for row in report.get("checks", []):
        lines.append(
            f"| {row.get('name')} | {row.get('passed')} | {row.get('detail')} | {row.get('report')} |"
        )
    return "\n".join(lines) + "\n"


def build_readiness_report(report_dir: Path) -> dict[str, Any]:
    checks = [
        _check_product_acceptance(report_dir),
        _check_frontend_e2e(report_dir),
        _check_loadtest(report_dir),
        _check_slo(report_dir, file_name="slo_latest.json", check_name="slo_degraded"),
        _check_slo(report_dir, file_name="slo_realtime_latest.json", check_name="slo_realtime"),
        _check_simple_bool(
            report_dir,
            file_name="dependency_fault_drill_latest.json",
            check_name="dependency_fault_drill",
        ),
        _check_simple_bool(
            report_dir,
            file_name="persistence_drill_latest.json",
            check_name="persistence_drill",
        ),
        _check_observability_stack(report_dir),
        _check_remote_ci(report_dir),
    ]
    rows = [item.as_dict() for item in checks]
    return {
        "generated_at": _now_utc(),
        "overall_passed": all(item.passed for item in checks),
        "checks": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate product readiness evidence reports")
    parser.add_argument("--report-dir", default=str(_DEFAULT_REPORT_DIR))
    parser.add_argument("--output-json", default=str(_DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(_DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    report_dir = Path(str(args.report_dir))
    report = build_readiness_report(report_dir)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"

    output_json = Path(str(args.output_json))
    output_md = Path(str(args.output_md))
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(rendered, encoding="utf-8")
    output_md.write_text(_render_markdown(report), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("overall_passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
