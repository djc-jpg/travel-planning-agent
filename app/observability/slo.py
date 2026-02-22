"""SLO objective evaluation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SLOCheckResult:
    name: str
    metric: str
    actual: float
    target: float
    op: str
    passed: bool


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _metric_from_snapshot(snapshot: dict[str, Any]) -> dict[str, float]:
    total_requests = max(1.0, _safe_float(snapshot.get("total_requests", 0)))
    degrade_counts = snapshot.get("degrade_counts", {})
    l0_count = _safe_float(degrade_counts.get("L0", 0)) if isinstance(degrade_counts, dict) else 0.0
    l3_count = _safe_float(degrade_counts.get("L3", 0)) if isinstance(degrade_counts, dict) else 0.0

    tool_calls = snapshot.get("tool_calls", {})
    tool_total = 0.0
    tool_error = 0.0
    if isinstance(tool_calls, dict):
        for row in tool_calls.values():
            if not isinstance(row, dict):
                continue
            tool_total += _safe_float(row.get("count", 0))
            tool_error += _safe_float(row.get("error", 0))
    tool_error_rate = (tool_error / tool_total) if tool_total > 0 else 0.0

    return {
        "success_rate": _safe_float(snapshot.get("success_rate", 0.0)),
        "p95_latency_ms": _safe_float(snapshot.get("p95_latency_ms", 0.0)),
        "l0_ratio": l0_count / total_requests,
        "l3_ratio": l3_count / total_requests,
        "tool_error_rate": tool_error_rate,
    }


def infer_slo_profile(snapshot: dict[str, Any], *, realtime_l0_ratio_min: float = 0.3) -> str:
    metrics = _metric_from_snapshot(snapshot)
    return "realtime" if metrics.get("l0_ratio", 0.0) >= max(0.0, float(realtime_l0_ratio_min)) else "degraded"


def resolve_slo_objectives(
    *,
    snapshot: dict[str, Any],
    objectives_config: Any,
    profile: str = "auto",
) -> tuple[str, list[dict[str, Any]]]:
    requested = str(profile or "auto").strip().lower() or "auto"

    # Backward compatibility: plain list means custom objectives only.
    if isinstance(objectives_config, list):
        return "custom", list(objectives_config)

    if not isinstance(objectives_config, dict):
        raise ValueError("SLO objectives file must be a JSON array or object")

    profiles = objectives_config.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("SLO objectives object must include non-empty 'profiles'")

    if requested == "auto":
        auto_config = objectives_config.get("auto")
        threshold = 0.3
        default_profile = "degraded"
        if isinstance(auto_config, dict):
            threshold = _safe_float(auto_config.get("realtime_l0_ratio_min"), default=0.3)
            default_profile = str(auto_config.get("default_profile", "degraded")).strip().lower() or "degraded"
        inferred = infer_slo_profile(snapshot, realtime_l0_ratio_min=threshold)
        selected_profile = inferred if inferred in profiles else default_profile
    else:
        selected_profile = requested

    selected = profiles.get(selected_profile)
    if not isinstance(selected, list):
        available = ", ".join(sorted(str(key) for key in profiles.keys()))
        raise ValueError(f"unknown SLO profile '{selected_profile}', available: {available}")
    return selected_profile, list(selected)


def _compare(actual: float, op: str, target: float) -> bool:
    if op == ">=":
        return actual >= target
    if op == "<=":
        return actual <= target
    if op == ">":
        return actual > target
    if op == "<":
        return actual < target
    if op == "==":
        return abs(actual - target) < 1e-9
    raise ValueError(f"unsupported operator: {op}")


def evaluate_slo_objectives(snapshot: dict[str, Any], objectives: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = _metric_from_snapshot(snapshot)
    checks: list[SLOCheckResult] = []
    for row in objectives:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip() or "unnamed_objective"
        metric = str(row.get("metric", "")).strip()
        op = str(row.get("op", ">=")).strip()
        target = _safe_float(row.get("target", 0.0))
        actual = _safe_float(metrics.get(metric, 0.0))
        passed = _compare(actual, op, target)
        checks.append(
            SLOCheckResult(
                name=name,
                metric=metric,
                actual=actual,
                target=target,
                op=op,
                passed=passed,
            )
        )

    failed = [row for row in checks if not row.passed]
    return {
        "passed": len(failed) == 0,
        "metrics": metrics,
        "checks": [
            {
                "name": row.name,
                "metric": row.metric,
                "actual": round(row.actual, 6),
                "target": row.target,
                "op": row.op,
                "passed": row.passed,
            }
            for row in checks
        ],
        "failed": [
            {
                "name": row.name,
                "metric": row.metric,
                "actual": round(row.actual, 6),
                "target": row.target,
                "op": row.op,
            }
            for row in failed
        ],
    }


__all__ = [
    "SLOCheckResult",
    "evaluate_slo_objectives",
    "infer_slo_profile",
    "resolve_slo_objectives",
]
