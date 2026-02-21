"""Rollout smoke checks for ENGINE_VERSION/STRICT_REQUIRED_FIELDS phases."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any, Mapping
from urllib import error, request

from dotenv import load_dotenv

TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class DrillResult:
    name: str
    status: str
    detail: str


def _as_bool(text: str | bool) -> bool:
    if isinstance(text, bool):
        return text
    return str(text).strip().lower() in TRUTHY


def _http_request(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    payload: Mapping[str, Any] | None = None,
    timeout: int = 60,
) -> tuple[int, Any]:
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)

    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = request.Request(url=url, method=method, headers=req_headers, data=body)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            status_code = int(resp.status)
            content = resp.read().decode("utf-8")
            parsed = json.loads(content) if content else None
            return status_code, parsed
    except error.HTTPError as exc:
        content = exc.read().decode("utf-8", errors="replace")
        parsed = None
        if content:
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = content
        return int(exc.code), parsed


def run_rollout_drill(
    *,
    base_url: str,
    env: Mapping[str, str],
    expect_engine: str,
    expect_strict: bool,
    timeout: int = 60,
) -> list[DrillResult]:
    root = base_url.rstrip("/")
    results: list[DrillResult] = []

    api_headers: dict[str, str] = {}
    api_token = (env.get("API_BEARER_TOKEN") or "").strip()
    if api_token:
        api_headers["Authorization"] = f"Bearer {api_token}"

    health_status, health_payload = _http_request("GET", f"{root}/health", timeout=timeout)
    if health_status == 200 and isinstance(health_payload, dict) and health_payload.get("status") == "ok":
        results.append(DrillResult("health", "PASS", "/health ok"))
    else:
        results.append(
            DrillResult("health", "FAIL", f"/health unexpected: status={health_status}, payload={health_payload}")
        )
        return results

    complete_status, complete_payload = _http_request(
        "POST",
        f"{root}/plan",
        headers=api_headers,
        payload={
            "message": "我想去杭州玩2天，2026-04-01到2026-04-02，预算每天800",
            "constraints": {
                "city": "杭州",
                "days": 2,
                "date_start": "2026-04-01",
                "date_end": "2026-04-02",
            },
        },
        timeout=timeout,
    )
    complete_ok = (
        complete_status == 200
        and isinstance(complete_payload, dict)
        and complete_payload.get("status") in {"done", "clarifying"}
    )
    if complete_ok:
        results.append(DrillResult("complete_request", "PASS", f"status={complete_payload.get('status')}"))
    else:
        results.append(
            DrillResult(
                "complete_request",
                "FAIL",
                f"unexpected response: status={complete_status}, payload={complete_payload}",
            )
        )

    missing_status, missing_payload = _http_request(
        "POST",
        f"{root}/plan",
        headers=api_headers,
        payload={"message": "帮我规划旅行"},
        timeout=timeout,
    )
    missing_actual = missing_payload.get("status") if isinstance(missing_payload, dict) else None
    if expect_strict:
        missing_ok = missing_status == 200 and missing_actual == "clarifying"
    else:
        missing_ok = missing_status == 200 and missing_actual in {"done", "clarifying"}
    if missing_ok:
        results.append(DrillResult("missing_fields_behavior", "PASS", f"status={missing_actual}"))
    else:
        results.append(
            DrillResult(
                "missing_fields_behavior",
                "FAIL",
                (
                    f"expected strict={expect_strict}, got status_code={missing_status}, "
                    f"status={missing_actual}, payload={missing_payload}"
                ),
            )
        )

    diagnostics_enabled = _as_bool(env.get("ENABLE_DIAGNOSTICS", "false"))
    diagnostics_token = (env.get("DIAGNOSTICS_TOKEN") or "").strip()
    if diagnostics_enabled and diagnostics_token:
        diag_status, diag_payload = _http_request(
            "GET",
            f"{root}/diagnostics",
            headers={"Authorization": f"Bearer {diagnostics_token}"},
            timeout=timeout,
        )
        if diag_status != 200 or not isinstance(diag_payload, dict):
            results.append(
                DrillResult(
                    "diagnostics_flags",
                    "FAIL",
                    f"/diagnostics unexpected: status={diag_status}, payload={diag_payload}",
                )
            )
        else:
            runtime_flags = diag_payload.get("runtime_flags", {})
            engine_actual = str(runtime_flags.get("engine_version", "")).lower()
            strict_actual = bool(runtime_flags.get("strict_required_fields"))
            if engine_actual == expect_engine.lower() and strict_actual == expect_strict:
                results.append(
                    DrillResult(
                        "diagnostics_flags",
                        "PASS",
                        f"engine={engine_actual}, strict={strict_actual}",
                    )
                )
            else:
                results.append(
                    DrillResult(
                        "diagnostics_flags",
                        "FAIL",
                        (
                            f"expected engine={expect_engine}, strict={expect_strict}; "
                            f"actual engine={engine_actual}, strict={strict_actual}"
                        ),
                    )
                )
    else:
        results.append(
            DrillResult(
                "diagnostics_flags",
                "WARN",
                "ENABLE_DIAGNOSTICS or DIAGNOSTICS_TOKEN not set; runtime flag verification skipped",
            )
        )

    return results


def _print_results(results: list[DrillResult]) -> None:
    print("== Rollout Drill ==")
    for item in results:
        print(f"[{item.status}] {item.name}: {item.detail}")
    print("")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run rollout smoke checks against a deployed backend")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--env-file", default=".env.prerelease")
    parser.add_argument("--expect-engine", choices=["v1", "v2"], required=True)
    parser.add_argument("--expect-strict", choices=["true", "false"], required=True)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    load_dotenv(args.env_file, override=False)
    env = dict(os.environ)

    results = run_rollout_drill(
        base_url=args.base_url,
        env=env,
        expect_engine=args.expect_engine,
        expect_strict=_as_bool(args.expect_strict),
        timeout=args.timeout,
    )
    _print_results(results)

    failed = any(item.status == "FAIL" for item in results)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

