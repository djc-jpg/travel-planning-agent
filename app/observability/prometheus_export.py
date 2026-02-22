"""Prometheus exposition renderer for in-process plan metrics."""

from __future__ import annotations

import time
from typing import Any

_STARTED_AT = time.time()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sanitize_label_value(value: Any) -> str:
    text = str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _metric_line(name: str, value: Any, labels: dict[str, Any] | None = None) -> str:
    if labels:
        rendered = ",".join(
            f'{str(key)}="{_sanitize_label_value(label_value)}"'
            for key, label_value in sorted(labels.items(), key=lambda item: item[0])
        )
        return f"{name}{{{rendered}}} {_safe_float(value)}"
    return f"{name} {_safe_float(value)}"


def render_prometheus_metrics(snapshot: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.extend(
        [
            "# HELP trip_agent_uptime_seconds Process uptime in seconds.",
            "# TYPE trip_agent_uptime_seconds gauge",
            _metric_line("trip_agent_uptime_seconds", max(0.0, time.time() - _STARTED_AT)),
            "",
            "# HELP trip_agent_requests_total Total number of planning requests observed.",
            "# TYPE trip_agent_requests_total counter",
            _metric_line("trip_agent_requests_total", snapshot.get("total_requests", 0)),
            "",
            "# HELP trip_agent_success_rate Ratio of successful requests (done/clarifying).",
            "# TYPE trip_agent_success_rate gauge",
            _metric_line("trip_agent_success_rate", snapshot.get("success_rate", 0.0)),
            "",
            "# HELP trip_agent_latency_p95_ms P95 request latency in milliseconds.",
            "# TYPE trip_agent_latency_p95_ms gauge",
            _metric_line("trip_agent_latency_p95_ms", snapshot.get("p95_latency_ms", 0.0)),
            "",
            "# HELP trip_agent_llm_calls_per_request Average LLM calls per request.",
            "# TYPE trip_agent_llm_calls_per_request gauge",
            _metric_line("trip_agent_llm_calls_per_request", snapshot.get("llm_calls_per_request", 0.0)),
            "",
        ]
    )

    for metric_name, labels, src in (
        ("trip_agent_request_status_total", {"status": None}, snapshot.get("status_counts", {})),
        ("trip_agent_engine_requests_total", {"engine": None}, snapshot.get("engine_counts", {})),
        ("trip_agent_strict_mode_requests_total", {"strict_mode": None}, snapshot.get("strict_required_fields", {})),
        ("trip_agent_degrade_level_total", {"degrade_level": None}, snapshot.get("degrade_counts", {})),
    ):
        lines.append(f"# HELP {metric_name} Counter with label breakdown.")
        lines.append(f"# TYPE {metric_name} counter")
        if isinstance(src, dict):
            label_key = next(iter(labels.keys()))
            for key, value in sorted(src.items(), key=lambda item: str(item[0])):
                lines.append(_metric_line(metric_name, value, labels={label_key: key}))
        lines.append("")

    tool_calls = snapshot.get("tool_calls", {})
    lines.extend(
        [
            "# HELP trip_agent_tool_calls_total Tool invocation totals by tool and status.",
            "# TYPE trip_agent_tool_calls_total counter",
        ]
    )
    if isinstance(tool_calls, dict):
        for tool, payload in sorted(tool_calls.items(), key=lambda item: str(item[0])):
            if not isinstance(payload, dict):
                continue
            ok_count = _safe_int(payload.get("ok", 0))
            err_count = _safe_int(payload.get("error", 0))
            lines.append(
                _metric_line(
                    "trip_agent_tool_calls_total",
                    ok_count,
                    labels={"tool": tool, "status": "ok"},
                )
            )
            lines.append(
                _metric_line(
                    "trip_agent_tool_calls_total",
                    err_count,
                    labels={"tool": tool, "status": "error"},
                )
            )
    lines.append("")

    lines.extend(
        [
            "# HELP trip_agent_tool_latency_p95_ms Tool call latency p95 by tool.",
            "# TYPE trip_agent_tool_latency_p95_ms gauge",
        ]
    )
    if isinstance(tool_calls, dict):
        for tool, payload in sorted(tool_calls.items(), key=lambda item: str(item[0])):
            if not isinstance(payload, dict):
                continue
            latency = payload.get("latency", {})
            if isinstance(latency, dict):
                lines.append(
                    _metric_line(
                        "trip_agent_tool_latency_p95_ms",
                        latency.get("p95_ms", 0.0),
                        labels={"tool": tool},
                    )
                )
    lines.append("")
    return "\n".join(lines).strip() + "\n"


__all__ = ["render_prometheus_metrics"]
