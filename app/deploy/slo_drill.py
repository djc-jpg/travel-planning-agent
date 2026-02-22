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


@dataclass(frozen=True)
class SLODrillConfig:
    host: str
    port: int
    request_count: int
    timeout_seconds: float
    objectives_file: Path
    profile: str
    output_file: Path


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _spawn_app(host: str, port: int) -> subprocess.Popen[str]:
    env = dict(os.environ)
    env.setdefault("ALLOW_UNAUTHENTICATED_API", "true")
    env.setdefault("STRICT_EXTERNAL_DATA", "false")
    env.setdefault("ROUTING_PROVIDER", "fixture")
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
        host,
        "--port",
        str(port),
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


def _post_plan(base_url: str) -> int:
    payload = {
        "message": "北京2天旅行，2026-04-01到2026-04-02",
        "constraints": {
            "city": "北京",
            "days": 2,
            "date_start": "2026-04-01",
            "date_end": "2026-04-02",
        },
    }
    with httpx.Client(timeout=_DEFAULT_TIMEOUT_SECONDS) as client:
        response = client.post(base_url.rstrip("/") + "/plan", json=payload)
    return response.status_code


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
    process = _spawn_app(config.host, config.port)
    started = time.perf_counter()
    statuses: list[int] = []
    try:
        _wait_for_health(base_url, timeout_seconds=config.timeout_seconds)
        for _ in range(max(1, config.request_count)):
            statuses.append(_post_plan(base_url))
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
    parser.add_argument("--output", default=str(_DEFAULT_OUTPUT))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config = SLODrillConfig(
        host=str(args.host),
        port=max(1, int(args.port)),
        request_count=max(1, int(args.requests)),
        timeout_seconds=max(5.0, float(args.timeout_seconds)),
        objectives_file=Path(str(args.objectives)),
        profile=str(args.profile),
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
