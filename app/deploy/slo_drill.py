"""Run a deterministic local SLO drill with synthetic traffic."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

from app.observability.slo import evaluate_slo_objectives, resolve_slo_objectives

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 18300
_DEFAULT_REQUESTS = 20
_DEFAULT_TIMEOUT_SECONDS = 30.0
_DEFAULT_OBJECTIVES = Path("deploy") / "observability" / "slo_objectives.json"
_DEFAULT_OUTPUT = Path("eval") / "reports" / "slo_latest.json"
_DEFAULT_ENV_FILE = ".env.prerelease"
_DEFAULT_REALTIME_WARMUP_REQUESTS = 3

_REALTIME_PAYLOADS = [
    {
        "message": "\u5317\u4eac1\u5929\u8f7b\u677e\u6e38\uff0c\u5386\u53f2\u6587\u5316\u4e3a\u4e3b\uff0c\u9884\u7b97\u9002\u4e2d",
        "constraints": {
            "city": "\u5317\u4eac",
            "days": 1,
            "date_start": "2026-04-01",
            "date_end": "2026-04-01",
            "budget_per_day": 1200,
            "pace": "relaxed",
            "transport_mode": "driving",
        },
    },
    {
        "message": "\u676d\u5dde1\u5929\u4f11\u95f2\u6e38\uff0c\u559c\u6b22\u56ed\u6797\u548c\u7f8e\u98df",
        "constraints": {
            "city": "\u676d\u5dde",
            "days": 1,
            "date_start": "2026-04-01",
            "date_end": "2026-04-01",
            "budget_per_day": 1200,
            "pace": "relaxed",
            "transport_mode": "driving",
        },
    },
    {
        "message": "\u4e0a\u6d771\u5929\u57ce\u5e02\u6f2b\u6b65\uff0c\u5730\u6807\u4e0e\u591c\u666f",
        "constraints": {
            "city": "\u4e0a\u6d77",
            "days": 1,
            "date_start": "2026-04-01",
            "date_end": "2026-04-01",
            "budget_per_day": 1200,
            "pace": "relaxed",
            "transport_mode": "driving",
        },
    },
]

_DEGRADED_PAYLOAD = {
    "message": "\u5317\u4eac2\u5929\u65c5\u884c\uff0c2026-04-01\u52302026-04-02",
    "constraints": {
        "city": "\u5317\u4eac",
        "days": 2,
        "date_start": "2026-04-01",
        "date_end": "2026-04-02",
    },
}


@dataclass(frozen=True)
class SLODrillConfig:
    host: str
    port: int
    request_count: int
    timeout_seconds: float
    objectives_file: Path
    profile: str
    env_file: Path
    use_env_file: bool
    strict_external_data: bool
    routing_provider: str
    warmup_requests: int
    output_file: Path


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def _spawn_app(config: SLODrillConfig) -> subprocess.Popen[str]:
    env = dict(os.environ)
    if config.use_env_file:
        env.update(_load_env_file(config.env_file))

    env.setdefault("ALLOW_UNAUTHENTICATED_API", "true")
    env["STRICT_EXTERNAL_DATA"] = "true" if config.strict_external_data else "false"
    env["ROUTING_PROVIDER"] = config.routing_provider
    env.setdefault("PLAN_PERSISTENCE_ENABLED", "false")
    env.setdefault("ENABLE_DIAGNOSTICS", "false")
    env.setdefault("RATE_LIMIT_MAX", "100000")
    env.setdefault("RATE_LIMIT_WINDOW", "60")
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.api.main:app",
        "--host",
        config.host,
        "--port",
        str(config.port),
    ]
    return subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _stop_app(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=8)
    except Exception:
        try:
            process.send_signal(signal.SIGKILL)
        except Exception:
            return


def _wait_for_health(base_url: str, timeout_seconds: float) -> None:
    deadline = time.time() + timeout_seconds
    with httpx.Client(timeout=3.0) as client:
        while time.time() < deadline:
            try:
                response = client.get(base_url.rstrip("/") + "/health")
                if response.status_code == 200:
                    return
            except Exception:
                pass
            time.sleep(0.2)
    raise RuntimeError(f"backend health check timed out: {base_url}")


def _next_payload(profile: str, index: int) -> dict[str, Any]:
    if profile == "realtime":
        payload = dict(_REALTIME_PAYLOADS[index % len(_REALTIME_PAYLOADS)])
        constraints = dict(payload.get("constraints", {}))
        days = max(1, int(constraints.get("days", 1)))
        start_date = date.today() + timedelta(days=1)
        end_date = start_date + timedelta(days=days - 1)
        constraints["date_start"] = start_date.isoformat()
        constraints["date_end"] = end_date.isoformat()
        payload["constraints"] = constraints
        return payload
    return dict(_DEGRADED_PAYLOAD)


def _post_plan(base_url: str, *, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    with httpx.Client(timeout=_DEFAULT_TIMEOUT_SECONDS) as client:
        response = client.post(base_url.rstrip("/") + "/plan", json=payload)
    body: dict[str, Any] = {}
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            body = parsed
    except Exception:
        body = {}
    return response.status_code, body


def _fetch_metrics(base_url: str) -> dict[str, Any]:
    with httpx.Client(timeout=10.0) as client:
        response = client.get(base_url.rstrip("/") + "/metrics")
    if response.status_code != 200:
        raise RuntimeError(f"metrics request failed: status={response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("metrics payload must be JSON object")
    return payload


def _calc_p95(values: list[float]) -> float:
    if not values:
        return 0.0
    rows = sorted(max(0.0, float(value)) for value in values)
    idx = max(0, min(len(rows) - 1, math.ceil(len(rows) * 0.95) - 1))
    return rows[idx]


def _build_eval_snapshot(
    *,
    statuses: list[int],
    result_statuses: list[str],
    latencies_ms: list[float],
    degrade_level_counts: dict[str, int],
    tool_calls: dict[str, Any],
) -> dict[str, Any]:
    total = max(1, len(statuses))
    success_count = 0
    for code, status in zip(statuses, result_statuses, strict=False):
        normalized_status = str(status or "").strip().lower()
        if code < 500 and normalized_status not in {"error"}:
            success_count += 1
    return {
        "total_requests": total,
        "success_rate": success_count / total,
        "p95_latency_ms": round(_calc_p95(latencies_ms), 2),
        "degrade_counts": dict(degrade_level_counts),
        "tool_calls": tool_calls,
    }


def run_slo_drill(config: SLODrillConfig) -> dict[str, Any]:
    base_url = f"http://{config.host}:{config.port}"
    process = _spawn_app(config)
    started = time.perf_counter()
    statuses: list[int] = []
    result_statuses: list[str] = []
    measured_latencies_ms: list[float] = []
    run_mode_counts: dict[str, int] = {}
    degrade_level_counts: dict[str, int] = {}
    fingerprints: list[dict[str, Any]] = []
    try:
        _wait_for_health(base_url, timeout_seconds=config.timeout_seconds)
        for warmup_index in range(max(0, config.warmup_requests)):
            warmup_payload = _next_payload(config.profile, warmup_index)
            _post_plan(base_url, payload=warmup_payload)

        for index in range(max(1, config.request_count)):
            payload = _next_payload(config.profile, index)
            request_started = time.perf_counter()
            status_code, body = _post_plan(base_url, payload=payload)
            measured_latencies_ms.append((time.perf_counter() - request_started) * 1000.0)
            statuses.append(status_code)
            if isinstance(body, dict):
                result_statuses.append(str(body.get("status", "")).strip().lower())
            else:
                result_statuses.append("")

            run_fp = body.get("run_fingerprint", {}) if isinstance(body, dict) else {}
            if isinstance(run_fp, dict):
                run_mode = str(run_fp.get("run_mode", "")).strip() or "UNKNOWN"
                run_mode_counts[run_mode] = run_mode_counts.get(run_mode, 0) + 1
                if len(fingerprints) < 3:
                    fingerprints.append(
                        {
                            "run_mode": run_mode,
                            "poi_provider": run_fp.get("poi_provider"),
                            "route_provider": run_fp.get("route_provider"),
                            "llm_provider": run_fp.get("llm_provider"),
                            "strict_external_data": run_fp.get("strict_external_data"),
                        }
                    )

            degrade_level = str(body.get("degrade_level", "")).strip() if isinstance(body, dict) else ""
            if degrade_level:
                degrade_level_counts[degrade_level] = degrade_level_counts.get(degrade_level, 0) + 1

        metrics_snapshot = _fetch_metrics(base_url)
    finally:
        _stop_app(process)

    objectives_config = _load_json(config.objectives_file)
    eval_snapshot = _build_eval_snapshot(
        statuses=statuses,
        result_statuses=result_statuses,
        latencies_ms=measured_latencies_ms,
        degrade_level_counts=degrade_level_counts,
        tool_calls=dict(metrics_snapshot.get("tool_calls", {})),
    )
    selected_profile, objectives = resolve_slo_objectives(
        snapshot=eval_snapshot,
        objectives_config=objectives_config,
        profile=config.profile,
    )
    report = evaluate_slo_objectives(eval_snapshot, objectives)

    report["profile"] = selected_profile
    report["objectives_file"] = str(config.objectives_file)
    report["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["request_count"] = max(1, config.request_count)
    report["warmup_request_count"] = max(0, config.warmup_requests)
    report["status_counts"] = {str(code): statuses.count(code) for code in sorted(set(statuses))}
    report["run_mode_counts"] = run_mode_counts
    report["degrade_level_counts"] = degrade_level_counts
    report["fingerprints"] = fingerprints
    report["strict_external_data"] = bool(config.strict_external_data)
    report["routing_provider"] = config.routing_provider
    report["env_file"] = str(config.env_file) if config.use_env_file else ""
    report["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
    report["steady_state_p95_latency_ms"] = round(_calc_p95(measured_latencies_ms), 2)
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local SLO drill and produce report")
    parser.add_argument("--host", default=_DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT)
    parser.add_argument("--requests", type=int, default=_DEFAULT_REQUESTS)
    parser.add_argument("--timeout-seconds", type=float, default=_DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--objectives", default=str(_DEFAULT_OBJECTIVES))
    parser.add_argument("--profile", default="degraded", choices=["auto", "realtime", "degraded"])
    parser.add_argument("--env-file", default=_DEFAULT_ENV_FILE)
    parser.add_argument("--no-env-file", action="store_true", help="do not load environment variables from env-file")
    parser.add_argument("--strict-external-data", default="", choices=["", "true", "false"])
    parser.add_argument("--routing-provider", default="", choices=["", "auto", "fixture", "real"])
    parser.add_argument("--warmup-requests", type=int, default=-1)
    parser.add_argument("--output", default=str(_DEFAULT_OUTPUT))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    profile = str(args.profile)
    strict_external_data = profile == "realtime"
    if str(args.strict_external_data).strip():
        strict_external_data = str(args.strict_external_data).strip().lower() == "true"
    routing_provider = "auto" if profile == "realtime" else "fixture"
    if str(args.routing_provider).strip():
        routing_provider = str(args.routing_provider).strip()

    warmup_requests = int(args.warmup_requests)
    if warmup_requests < 0:
        warmup_requests = _DEFAULT_REALTIME_WARMUP_REQUESTS if profile == "realtime" else 0

    config = SLODrillConfig(
        host=str(args.host),
        port=max(1, int(args.port)),
        request_count=max(1, int(args.requests)),
        timeout_seconds=max(5.0, float(args.timeout_seconds)),
        objectives_file=Path(str(args.objectives)),
        profile=profile,
        env_file=Path(str(args.env_file)),
        use_env_file=not bool(args.no_env_file),
        strict_external_data=bool(strict_external_data),
        routing_provider=routing_provider,
        warmup_requests=max(0, warmup_requests),
        output_file=Path(str(args.output)),
    )
    report = run_slo_drill(config)

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    config.output_file.parent.mkdir(parents=True, exist_ok=True)
    config.output_file.write_text(rendered + "\n", encoding="utf-8")
    return 0 if bool(report.get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
