"""In-process metrics for plan_trip runtime behavior."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass


@dataclass
class _LatencyAgg:
    total_ms: float = 0.0
    count: int = 0
    max_ms: float = 0.0
    values: list[float] | None = None

    def __post_init__(self) -> None:
        if self.values is None:
            self.values = []

    def add(self, value_ms: float) -> None:
        val = max(0.0, float(value_ms))
        self.total_ms += val
        self.count += 1
        if val > self.max_ms:
            self.max_ms = val
        self.values.append(val)
        if len(self.values) > 5000:
            self.values = self.values[-5000:]

    def p95(self) -> float:
        if not self.values:
            return 0.0
        rows = sorted(self.values)
        idx = max(0, min(len(rows) - 1, math.ceil(len(rows) * 0.95) - 1))
        return rows[idx]

    def snapshot(self) -> dict[str, float]:
        avg_ms = (self.total_ms / self.count) if self.count else 0.0
        return {
            "count": self.count,
            "avg_ms": round(avg_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "p95_ms": round(self.p95(), 2),
        }


class PlanMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_requests = 0
        self._status_counts: dict[str, int] = {}
        self._engine_counts: dict[str, int] = {}
        self._strict_counts: dict[str, int] = {"true": 0, "false": 0}
        self._degrade_counts: dict[str, int] = {}
        self._latency = _LatencyAgg()
        self._tool_stats: dict[str, dict[str, object]] = {}
        self._success_requests = 0
        self._total_llm_calls = 0
        self._history: list[dict[str, object]] = []

    def record(
        self,
        *,
        status: str,
        engine_version: str,
        strict_required_fields: bool,
        latency_ms: float,
        request_id: str = "",
        trace_id: str = "",
        degrade_level: str = "L0",
        llm_call_count: int = 0,
        repair_loop_count: int = 0,
    ) -> None:
        key_status = status or "unknown"
        key_engine = (engine_version or "unknown").lower()
        strict_key = "true" if strict_required_fields else "false"
        degrade_key = degrade_level or "L0"
        llm_calls = max(0, int(llm_call_count))
        repairs = max(0, int(repair_loop_count))

        with self._lock:
            self._total_requests += 1
            self._status_counts[key_status] = self._status_counts.get(key_status, 0) + 1
            self._engine_counts[key_engine] = self._engine_counts.get(key_engine, 0) + 1
            self._strict_counts[strict_key] = self._strict_counts.get(strict_key, 0) + 1
            self._degrade_counts[degrade_key] = self._degrade_counts.get(degrade_key, 0) + 1
            self._latency.add(latency_ms)
            self._total_llm_calls += llm_calls
            if key_status in {"done", "clarifying"}:
                self._success_requests += 1

            self._history.append(
                {
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "engine_version": key_engine,
                    "strict_mode": bool(strict_required_fields),
                    "degrade_level": degrade_key,
                    "llm_call_count": llm_calls,
                    "repair_loop_count": repairs,
                    "latency_ms": round(max(0.0, float(latency_ms)), 2),
                    "status": key_status,
                }
            )
            if len(self._history) > 200:
                self._history = self._history[-200:]

    def record_tool_call(
        self,
        *,
        tool_name: str,
        latency_ms: float,
        ok: bool,
        error_code: str = "",
        returned_count: int = 0,
    ) -> None:
        key = (tool_name or "unknown").strip().lower() or "unknown"
        latency_val = max(0.0, float(latency_ms))
        returned = max(0, int(returned_count))
        err = (error_code or "").strip()

        with self._lock:
            row = self._tool_stats.get(key)
            if row is None:
                row = {
                    "count": 0,
                    "ok": 0,
                    "error": 0,
                    "returned_total": 0,
                    "latency": _LatencyAgg(),
                    "error_codes": {},
                }
                self._tool_stats[key] = row

            row["count"] = int(row["count"]) + 1
            row["returned_total"] = int(row["returned_total"]) + returned
            row_latency = row["latency"]
            if isinstance(row_latency, _LatencyAgg):
                row_latency.add(latency_val)
            if ok:
                row["ok"] = int(row["ok"]) + 1
            else:
                row["error"] = int(row["error"]) + 1
                if err:
                    error_codes = row["error_codes"]
                    if isinstance(error_codes, dict):
                        error_codes[err] = int(error_codes.get(err, 0)) + 1

    def _tool_snapshot(self) -> dict[str, object]:
        output: dict[str, object] = {}
        for tool_name, row in self._tool_stats.items():
            count = int(row.get("count", 0))
            ok = int(row.get("ok", 0))
            error = int(row.get("error", 0))
            returned_total = int(row.get("returned_total", 0))
            latency_payload = {"count": 0, "avg_ms": 0.0, "max_ms": 0.0, "p95_ms": 0.0}
            row_latency = row.get("latency")
            if isinstance(row_latency, _LatencyAgg):
                latency_payload = row_latency.snapshot()
            output[tool_name] = {
                "count": count,
                "ok": ok,
                "error": error,
                "success_rate": round((ok / count), 4) if count else 0.0,
                "avg_returned_count": round((returned_total / count), 2) if count else 0.0,
                "latency": latency_payload,
                "error_codes": dict(row.get("error_codes", {})),
            }
        return output

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            success_rate = (
                self._success_requests / self._total_requests
                if self._total_requests
                else 0.0
            )
            llm_calls_per_request = (
                self._total_llm_calls / self._total_requests
                if self._total_requests
                else 0.0
            )
            return {
                "total_requests": self._total_requests,
                "status_counts": dict(self._status_counts),
                "engine_counts": dict(self._engine_counts),
                "strict_required_fields": dict(self._strict_counts),
                "degrade_counts": dict(self._degrade_counts),
                "latency": self._latency.snapshot(),
                "p95_latency_ms": round(self._latency.p95(), 2),
                "success_rate": round(success_rate, 4),
                "llm_calls_per_request": round(llm_calls_per_request, 4),
                "tool_calls": self._tool_snapshot(),
                "last_requests": list(self._history),
            }

    def reset(self) -> None:
        with self._lock:
            self._total_requests = 0
            self._status_counts = {}
            self._engine_counts = {}
            self._strict_counts = {"true": 0, "false": 0}
            self._degrade_counts = {}
            self._latency = _LatencyAgg()
            self._tool_stats = {}
            self._success_requests = 0
            self._total_llm_calls = 0
            self._history = []


_metrics_lock = threading.Lock()
_metrics: PlanMetrics | None = None


def get_plan_metrics() -> PlanMetrics:
    global _metrics
    with _metrics_lock:
        if _metrics is None:
            _metrics = PlanMetrics()
        return _metrics


def observe_plan_request(
    *,
    status: str,
    engine_version: str,
    strict_required_fields: bool,
    latency_ms: float,
    request_id: str = "",
    trace_id: str = "",
    degrade_level: str = "L0",
    llm_call_count: int = 0,
    repair_loop_count: int = 0,
) -> None:
    get_plan_metrics().record(
        status=status,
        engine_version=engine_version,
        strict_required_fields=strict_required_fields,
        latency_ms=latency_ms,
        request_id=request_id,
        trace_id=trace_id,
        degrade_level=degrade_level,
        llm_call_count=llm_call_count,
        repair_loop_count=repair_loop_count,
    )


def observe_tool_call(
    *,
    tool_name: str,
    latency_ms: float,
    ok: bool,
    error_code: str = "",
    returned_count: int = 0,
) -> None:
    get_plan_metrics().record_tool_call(
        tool_name=tool_name,
        latency_ms=latency_ms,
        ok=ok,
        error_code=error_code,
        returned_count=returned_count,
    )


__all__ = ["PlanMetrics", "get_plan_metrics", "observe_plan_request", "observe_tool_call"]
