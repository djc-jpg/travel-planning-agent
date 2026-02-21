"""Release validation summary helper.

Aggregates latest eval + release gate reports into one compact status view.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

_DEFAULT_GATE_REPORT = Path("eval") / "reports" / "release_gate_latest.json"
_DEFAULT_EVAL_REPORT_DIR = Path("app") / "eval" / "reports"
_TRACKED_GATE_METRICS = (
    "unknown_fact_rate",
    "verified_fact_ratio",
    "l0_real_routing_ratio",
    "routing_fixture_rate",
    "fallback_rate",
    "edit_roundtrip_pass_rate",
    "schema_valid_rate",
    "constraint_satisfaction_rate",
    "travel_feasibility_rate",
    "clarifying_correctness",
    "plan_success_rate",
    "concurrency_isolation",
    "p95_latency_ms",
)


def _read_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"report payload must be a JSON object: {path}")
    return payload


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    safe_ratio = max(0.0, min(1.0, ratio))
    idx = max(0, min(len(ordered) - 1, int(len(ordered) * safe_ratio + 0.999999) - 1))
    return ordered[idx]


def _confidence_from_rows(case_rows: Any) -> dict[str, Any]:
    if not isinstance(case_rows, list):
        return {"samples": 0, "mean": None, "p50": None, "p90": None}

    scores: list[float] = []
    for row in case_rows:
        if not isinstance(row, dict):
            continue
        value = row.get("confidence_score_case")
        if isinstance(value, (int, float)):
            scores.append(float(value))

    if not scores:
        return {"samples": 0, "mean": None, "p50": None, "p90": None}

    mean = sum(scores) / len(scores)
    return {
        "samples": len(scores),
        "mean": round(mean, 4),
        "p50": round(_percentile(scores, 0.5), 4),
        "p90": round(_percentile(scores, 0.9), 4),
    }


def load_latest_eval_report(eval_report_dir: Path) -> tuple[Path, dict[str, Any]] | None:
    candidates = sorted(eval_report_dir.glob("eval_*.json"))
    target: Path | None = candidates[-1] if candidates else None
    if target is None:
        latest = eval_report_dir / "latest.json"
        if latest.exists():
            target = latest
    if target is None:
        return None
    return target, _read_json(target)


def build_summary(
    *,
    release_gate_report: dict[str, Any],
    release_gate_path: Path,
    eval_report: dict[str, Any] | None = None,
    eval_path: Path | None = None,
) -> dict[str, Any]:
    metrics = release_gate_report.get("metrics", {})
    metrics = metrics if isinstance(metrics, dict) else {}

    tracked_metrics: dict[str, float | None] = {}
    for key in _TRACKED_GATE_METRICS:
        value = _coerce_float(metrics.get(key))
        tracked_metrics[key] = round(value, 4) if value is not None else None

    confidence_samples = int(metrics.get("confidence_samples", 0)) if isinstance(
        metrics.get("confidence_samples"), (int, float)
    ) else 0
    confidence_mean = _coerce_float(metrics.get("confidence_mean"))
    confidence_p50 = _coerce_float(metrics.get("confidence_p50"))
    confidence_p90 = _coerce_float(metrics.get("confidence_p90"))

    if confidence_samples > 0 and None not in (confidence_mean, confidence_p50, confidence_p90):
        confidence = {
            "samples": confidence_samples,
            "mean": round(float(confidence_mean), 4),
            "p50": round(float(confidence_p50), 4),
            "p90": round(float(confidence_p90), 4),
        }
    else:
        confidence = _confidence_from_rows(release_gate_report.get("case_rows"))

    eval_summary: dict[str, Any] | None = None
    if isinstance(eval_report, dict):
        eval_summary = {
            "average_score": _coerce_float(eval_report.get("average_score")),
            "pass_rate": _coerce_float(eval_report.get("pass_rate")),
            "passed": eval_report.get("passed"),
            "total_cases": eval_report.get("total_cases"),
        }

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "release_gate_passed": bool(release_gate_report.get("passed")),
        "release_gate_report": str(release_gate_path),
        "eval_report": str(eval_path) if eval_path is not None else None,
        "metrics": tracked_metrics,
        "confidence": confidence,
        "eval": eval_summary,
    }


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    if value is None:
        return "n/a"
    return str(value)


def render_summary_text(summary: dict[str, Any]) -> str:
    metrics = summary.get("metrics", {})
    confidence = summary.get("confidence", {})
    eval_payload = summary.get("eval")

    lines = [
        "release_summary",
        f"- generated_at: {summary.get('generated_at')}",
        f"- release_gate_passed: {summary.get('release_gate_passed')}",
        f"- release_gate_report: {summary.get('release_gate_report')}",
        f"- eval_report: {summary.get('eval_report') or 'n/a'}",
        f"- unknown_fact_rate: {_fmt(metrics.get('unknown_fact_rate'))}",
        f"- verified_fact_ratio: {_fmt(metrics.get('verified_fact_ratio'))}",
        f"- l0_real_routing_ratio: {_fmt(metrics.get('l0_real_routing_ratio'))}",
        f"- routing_fixture_rate: {_fmt(metrics.get('routing_fixture_rate'))}",
        f"- fallback_rate: {_fmt(metrics.get('fallback_rate'))}",
        f"- edit_roundtrip_pass_rate: {_fmt(metrics.get('edit_roundtrip_pass_rate'))}",
        f"- confidence_mean: {_fmt(confidence.get('mean'))}",
        f"- confidence_p50: {_fmt(confidence.get('p50'))}",
        f"- confidence_p90: {_fmt(confidence.get('p90'))}",
        f"- confidence_samples: {confidence.get('samples', 0)}",
    ]
    if isinstance(eval_payload, dict):
        lines.extend(
            [
                f"- eval_average_score: {_fmt(eval_payload.get('average_score'))}",
                f"- eval_pass_rate: {_fmt(eval_payload.get('pass_rate'))}",
                f"- eval_passed: {eval_payload.get('passed')}",
                f"- eval_total_cases: {eval_payload.get('total_cases')}",
            ]
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize release gate + eval signals")
    parser.add_argument("--release-gate-report", default=str(_DEFAULT_GATE_REPORT))
    parser.add_argument("--eval-report-dir", default=str(_DEFAULT_EVAL_REPORT_DIR))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--output", default="")
    parser.add_argument("--fail-on-gate-fail", action="store_true")
    args = parser.parse_args(argv)

    gate_path = Path(args.release_gate_report)
    eval_dir = Path(args.eval_report_dir)
    try:
        gate_report = _read_json(gate_path)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"failed_to_load_release_gate_report: {exc}")
        return 1

    eval_pair = load_latest_eval_report(eval_dir)
    eval_path: Path | None = None
    eval_report: dict[str, Any] | None = None
    if eval_pair is not None:
        eval_path, eval_report = eval_pair

    summary = build_summary(
        release_gate_report=gate_report,
        release_gate_path=gate_path,
        eval_report=eval_report,
        eval_path=eval_path,
    )

    if args.format == "json":
        rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    else:
        rendered = render_summary_text(summary)
    print(rendered)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")

    if args.fail_on_gate_fail and not summary.get("release_gate_passed", False):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
