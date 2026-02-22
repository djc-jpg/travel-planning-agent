"""Dependency fault drill runner (rate-limit/timeout/degrade/fail-fast)."""

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
from typing import Any, Callable

import httpx

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_BASE_PORT = 18200


@dataclass(frozen=True)
class DrillScenario:
    name: str
    description: str
    env_overrides: dict[str, str]
    check: Callable[[str], tuple[bool, str, dict[str, Any]]]


def _spawn_app(*, host: str, port: int, env_overrides: dict[str, str]) -> subprocess.Popen[str]:
    env = dict(os.environ)
    # Keep drill deterministic across environments: avoid accidentally picking
    # up repository .env / host-level real credentials unless explicitly asked.
    for key in ("AMAP_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"):
        env[key] = ""
    env.setdefault("ALLOW_UNAUTHENTICATED_API", "true")
    env.setdefault("STRICT_EXTERNAL_DATA", "false")
    env.setdefault("ROUTING_PROVIDER", "fixture")
    env.setdefault("PLAN_PERSISTENCE_ENABLED", "false")
    env.setdefault("ENABLE_DIAGNOSTICS", "false")
    env.setdefault("ENABLE_TOOL_FAULT_INJECTION", "false")
    env.update(env_overrides)

    cmd = [
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
        cmd,
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


def _wait_for_health(base_url: str, timeout_seconds: float = 45.0) -> None:
    deadline = time.time() + timeout_seconds
    with httpx.Client(timeout=5.0) as client:
        while time.time() < deadline:
            try:
                resp = client.get(base_url.rstrip("/") + "/health")
                if resp.status_code == 200:
                    return
            except Exception:
                pass
            time.sleep(0.3)
    raise RuntimeError(f"backend health check timed out: {base_url}")


def _post_plan(base_url: str, payload: dict[str, Any]) -> httpx.Response:
    with httpx.Client(timeout=20.0) as client:
        return client.post(base_url.rstrip("/") + "/plan", json=payload)


def _compact_plan_body(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {}
    run_fp = body.get("run_fingerprint")
    run_mode = run_fp.get("run_mode") if isinstance(run_fp, dict) else None
    message = body.get("message")
    detail = body.get("detail")
    return {
        "status": body.get("status"),
        "message": str(message)[:160] if message is not None else "",
        "detail": str(detail)[:160] if detail is not None else "",
        "degrade_level": body.get("degrade_level"),
        "run_mode": run_mode,
    }


def _scenario_degraded_baseline(base_url: str) -> tuple[bool, str, dict[str, Any]]:
    payload = {
        "message": "北京2天旅行，2026-04-01到2026-04-02",
        "constraints": {
            "city": "北京",
            "days": 2,
            "date_start": "2026-04-01",
            "date_end": "2026-04-02",
        },
    }
    resp = _post_plan(base_url, payload)
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    run_fp = body.get("run_fingerprint", {}) if isinstance(body, dict) else {}
    ok = (
        resp.status_code == 200
        and isinstance(body, dict)
        and str(body.get("status")) in {"done", "clarifying"}
        and str(run_fp.get("run_mode", "")) == "DEGRADED"
    )
    detail = f"status_code={resp.status_code}, status={body.get('status')}, run_mode={run_fp.get('run_mode')}"
    return ok, detail, {"status_code": resp.status_code, "body": _compact_plan_body(body)}


def _scenario_strict_fail_fast(base_url: str) -> tuple[bool, str, dict[str, Any]]:
    payload = {
        "message": "丽江2天旅行，2026-05-01到2026-05-02",
        "constraints": {
            "city": "丽江",
            "days": 2,
            "date_start": "2026-05-01",
            "date_end": "2026-05-02",
        },
    }
    resp = _post_plan(base_url, payload)
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    # In strict mode without external keys, both 422/500 are acceptable fail-fast
    # outcomes as long as the API returns a controlled JSON error response.
    detail_text = str(body.get("detail", "")) if isinstance(body, dict) else ""
    ok = resp.status_code in {422, 500} and bool(detail_text)
    detail = f"status_code={resp.status_code}, detail={detail_text[:120]}"
    return ok, detail, {"status_code": resp.status_code, "body": _compact_plan_body(body)}


def _scenario_tool_fault_timeout(base_url: str) -> tuple[bool, str, dict[str, Any]]:
    payload = {
        "message": "丽江2天旅行，2026-05-01到2026-05-02",
        "constraints": {
            "city": "丽江",
            "days": 2,
            "date_start": "2026-05-01",
            "date_end": "2026-05-02",
        },
    }
    resp = _post_plan(base_url, payload)
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    ok = resp.status_code == 422
    detail = f"status_code={resp.status_code}, detail={str(body.get('detail', ''))[:120]}"
    return ok, detail, {"status_code": resp.status_code, "body": _compact_plan_body(body)}


def _scenario_tool_fault_rate_limit(base_url: str) -> tuple[bool, str, dict[str, Any]]:
    payload = {
        "message": "丽江2天旅行，2026-05-01到2026-05-02",
        "constraints": {
            "city": "丽江",
            "days": 2,
            "date_start": "2026-05-01",
            "date_end": "2026-05-02",
        },
    }
    resp = _post_plan(base_url, payload)
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    ok = resp.status_code == 422
    detail = f"status_code={resp.status_code}, detail={str(body.get('detail', ''))[:120]}"
    return ok, detail, {"status_code": resp.status_code, "body": _compact_plan_body(body)}


def _scenario_api_rate_limit_guard(base_url: str) -> tuple[bool, str, dict[str, Any]]:
    payload = {"message": "帮我规划旅行"}
    statuses: list[int] = []
    with httpx.Client(timeout=20.0) as client:
        for _ in range(6):
            resp = client.post(base_url.rstrip("/") + "/plan", json=payload)
            statuses.append(resp.status_code)
    has_429 = any(code == 429 for code in statuses)
    has_500 = any(code >= 500 for code in statuses)
    ok = has_429 and not has_500
    detail = f"statuses={statuses}"
    return ok, detail, {"statuses": statuses}


def _scenarios() -> list[DrillScenario]:
    return [
        DrillScenario(
            name="degraded_baseline",
            description="No external keys in non-strict mode still returns DEGRADED response.",
            env_overrides={
                "STRICT_EXTERNAL_DATA": "false",
                "ROUTING_PROVIDER": "fixture",
            },
            check=_scenario_degraded_baseline,
        ),
        DrillScenario(
            name="strict_external_fail_fast",
            description="Strict external mode without keys must fail fast with controlled error.",
            env_overrides={
                "STRICT_EXTERNAL_DATA": "true",
                "ROUTING_PROVIDER": "auto",
            },
            check=_scenario_strict_fail_fast,
        ),
        DrillScenario(
            name="tool_timeout_fault",
            description="Injected upstream timeout should produce controlled 4xx business failure (not 5xx).",
            env_overrides={
                "ENABLE_TOOL_FAULT_INJECTION": "true",
                "TOOL_FAULT_INJECTION": "poi:timeout",
                "TOOL_FAULT_RATE": "1.0",
                "STRICT_EXTERNAL_DATA": "false",
            },
            check=_scenario_tool_fault_timeout,
        ),
        DrillScenario(
            name="tool_rate_limit_fault",
            description="Injected upstream 429 should produce controlled business failure (not crash).",
            env_overrides={
                "ENABLE_TOOL_FAULT_INJECTION": "true",
                "TOOL_FAULT_INJECTION": "poi:rate_limit",
                "TOOL_FAULT_RATE": "1.0",
                "STRICT_EXTERNAL_DATA": "false",
            },
            check=_scenario_tool_fault_rate_limit,
        ),
        DrillScenario(
            name="api_rate_limit_guard",
            description="API-level rate limiter should return 429 under burst traffic.",
            env_overrides={
                "RATE_LIMIT_MAX": "2",
                "RATE_LIMIT_WINDOW": "60",
                "STRICT_REQUIRED_FIELDS": "true",
                "ENGINE_VERSION": "v2",
            },
            check=_scenario_api_rate_limit_guard,
        ),
    ]


def run_dependency_fault_drill(*, host: str, base_port: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index, scenario in enumerate(_scenarios()):
        port = base_port + index
        base_url = f"http://{host}:{port}"
        process = _spawn_app(host=host, port=port, env_overrides=scenario.env_overrides)
        started = time.perf_counter()
        try:
            _wait_for_health(base_url)
            passed, detail, evidence = scenario.check(base_url)
        except Exception as exc:
            passed = False
            detail = f"drill_error: {type(exc).__name__}: {exc}"
            evidence = {}
        finally:
            _stop_app(process)
        rows.append(
            {
                "name": scenario.name,
                "description": scenario.description,
                "passed": passed,
                "detail": detail,
                "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2),
                "evidence": evidence,
            }
        )

    failures = [row for row in rows if not row.get("passed")]
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "passed": len(failures) == 0,
        "scenarios": rows,
        "failed": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run dependency fault drill scenarios")
    parser.add_argument("--host", default=_DEFAULT_HOST)
    parser.add_argument("--base-port", type=int, default=_DEFAULT_BASE_PORT)
    parser.add_argument("--output", default=str(Path("eval") / "reports" / "dependency_fault_drill_latest.json"))
    args = parser.parse_args(argv)

    report = run_dependency_fault_drill(host=str(args.host), base_port=int(args.base_port))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    output = Path(str(args.output))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if bool(report.get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
