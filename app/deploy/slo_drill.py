"""Run a deterministic local SLO drill with synthetic traffic."""

from __future__ import annotations

import argparse
import json
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
_REALTIME_PAYLOADS = [
    {
        "message": "北京1天轻松游，历史文化为主，预算适中",
        "constraints": {"city": "北京", "days": 1, "date_start": "2026-04-01", "date_end": "2026-04-01"},
    },
    {
        "message": "杭州1天休闲游，喜欢园林和美食",
        "constraints": {"city": "杭州", "days": 1, "date_start": "2026-04-01", "date_end": "2026-04-01"},
    },
    {
        "message": "上海1天城市漫步，地标与夜景",
        "constraints": {"city": "上海", "days": 1, "date_start": "2026-04-01", "date_end": "2026-04-01"},
    },
]
_DEGRADED_PAYLOAD = {
    "message": "北京2天旅行，2026-04-01到2026-04-02",
    "constraints": {
        "city": "北京",
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


def run_slo_drill(config: SLODrillConfig) -> dict[str, Any]:
    base_url = f"http://{config.host}:{config.port}"
    process = _spawn_app(config)
    started = time.perf_counter()
    statuses: list[int] = []
    run_mode_counts: dict[str, int] = {}
    degrade_level_counts: dict[str, int] = {}
    fingerprints: list[dict[str, Any]] = []
    try:
        _wait_for_health(base_url, timeout_seconds=config.timeout_seconds)
        for index in range(max(1, config.request_count)):
            payload = _next_payload(config.profile, index)
            status_code, body = _post_plan(base_url, payload=payload)
            statuses.append(status_code)
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
        snapshot = _fetch_metrics(base_url)
    finally:
        _stop_app(process)

    objectives_config = _load_json(config.objectives_file)
    selected_profile, objectives = resolve_slo_objectives(
        snapshot=snapshot,
        objectives_config=objectives_config,
        profile=config.profile,
    )
    report = evaluate_slo_objectives(snapshot, objectives)
    report["profile"] = selected_profile
    report["objectives_file"] = str(config.objectives_file)
    report["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["request_count"] = max(1, config.request_count)
    report["status_counts"] = {str(code): statuses.count(code) for code in sorted(set(statuses))}
    report["run_mode_counts"] = run_mode_counts
    report["degrade_level_counts"] = degrade_level_counts
    report["fingerprints"] = fingerprints
    report["strict_external_data"] = bool(config.strict_external_data)
    report["routing_provider"] = config.routing_provider
    report["env_file"] = str(config.env_file) if config.use_env_file else ""
    report["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
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
