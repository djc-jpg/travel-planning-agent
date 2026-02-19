"""Pre-release checks for environment and API smoke tests."""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib import error, request

from dotenv import load_dotenv

TRUTHY = {"1", "true", "yes", "on"}
PLACEHOLDER_MARKERS = ("<YOUR_", "YOUR_", "REPLACE_ME", "CHANGE_ME", "TODO")


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str


def _is_enabled(value: str | None) -> bool:
    return bool(value and value.strip().lower() in TRUTHY)


def _is_configured(value: str | None) -> bool:
    if not value:
        return False

    stripped = value.strip()
    if not stripped:
        return False

    upper = stripped.upper()
    return not any(marker in upper for marker in PLACEHOLDER_MARKERS)


def _as_positive_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _check_redis_connectivity(redis_url: str, allow_memory_fallback: bool = False) -> CheckResult:
    try:
        import redis
    except Exception:
        return CheckResult(
            "session_backend",
            "WARN",
            "redis dependency missing; connectivity check skipped",
        )

    try:
        client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        return CheckResult("session_backend", "PASS", "Redis session backend is reachable")
    except Exception as exc:
        if allow_memory_fallback:
            return CheckResult(
                "session_backend",
                "WARN",
                f"Redis unreachable ({type(exc).__name__}); fallback to in-memory backend is allowed",
            )
        return CheckResult(
            "session_backend",
            "FAIL",
            f"REDIS_URL is configured but unreachable: {type(exc).__name__}",
        )


def validate_environment(env: Mapping[str, str], runtime_checks: bool = False) -> list[CheckResult]:
    results: list[CheckResult] = []

    allow_unauthenticated_api = _is_enabled(env.get("ALLOW_UNAUTHENTICATED_API"))
    api_token = env.get("API_BEARER_TOKEN")
    if _is_configured(api_token):
        results.append(CheckResult("api_auth", "PASS", "API bearer auth is configured"))
    elif allow_unauthenticated_api:
        results.append(
            CheckResult(
                "api_auth",
                "WARN",
                "API auth disabled by ALLOW_UNAUTHENTICATED_API=true",
            )
        )
    else:
        results.append(
            CheckResult(
                "api_auth",
                "FAIL",
                "API_BEARER_TOKEN is missing; set token or ALLOW_UNAUTHENTICATED_API=true",
            )
        )

    diagnostics_enabled = _is_enabled(env.get("ENABLE_DIAGNOSTICS"))
    diagnostics_token = env.get("DIAGNOSTICS_TOKEN")
    if diagnostics_enabled and not _is_configured(diagnostics_token):
        results.append(
            CheckResult(
                "diagnostics_auth",
                "FAIL",
                "ENABLE_DIAGNOSTICS=true requires DIAGNOSTICS_TOKEN",
            )
        )
    elif diagnostics_enabled:
        results.append(CheckResult("diagnostics_auth", "PASS", "Diagnostics auth is configured"))
    else:
        results.append(CheckResult("diagnostics_auth", "PASS", "Diagnostics endpoint is disabled"))

    strict_external = _is_enabled(env.get("STRICT_EXTERNAL_DATA"))
    amap_key = env.get("AMAP_API_KEY")
    if strict_external and not _is_configured(amap_key):
        results.append(
            CheckResult(
                "strict_external_data",
                "FAIL",
                "STRICT_EXTERNAL_DATA=true requires AMAP_API_KEY",
            )
        )
    elif strict_external:
        results.append(CheckResult("strict_external_data", "PASS", "Strict external data mode enabled"))
    else:
        results.append(
            CheckResult("strict_external_data", "WARN", "Strict external data mode is disabled")
        )

    cors_origins = (env.get("CORS_ORIGINS") or "").strip()
    allow_credentials = _is_enabled(env.get("CORS_ALLOW_CREDENTIALS"))
    if cors_origins == "*":
        status_value = "FAIL" if allow_credentials else "WARN"
        detail = (
            "CORS_ORIGINS='*' with credentials is unsafe"
            if allow_credentials
            else "CORS_ORIGINS='*' allows any origin"
        )
        results.append(CheckResult("cors_policy", status_value, detail))
    else:
        results.append(CheckResult("cors_policy", "PASS", "CORS origin policy is scoped"))

    graph_timeout = _as_positive_int(env.get("GRAPH_TIMEOUT_SECONDS") or "120")
    if graph_timeout is None:
        results.append(CheckResult("graph_timeout", "FAIL", "GRAPH_TIMEOUT_SECONDS must be > 0"))
    else:
        results.append(CheckResult("graph_timeout", "PASS", f"Graph timeout is {graph_timeout}s"))

    rate_limit_max = _as_positive_int(env.get("RATE_LIMIT_MAX") or "60")
    rate_limit_window = _as_positive_int(env.get("RATE_LIMIT_WINDOW") or "60")
    if rate_limit_max is None or rate_limit_window is None:
        results.append(
            CheckResult(
                "rate_limit",
                "FAIL",
                "RATE_LIMIT_MAX and RATE_LIMIT_WINDOW must be positive integers",
            )
        )
    else:
        results.append(
            CheckResult(
                "rate_limit",
                "PASS",
                f"Rate limit configured to {rate_limit_max} req/{rate_limit_window}s",
            )
        )

    allow_memory_backend = _is_enabled(env.get("ALLOW_INMEMORY_BACKEND"))
    redis_url = env.get("REDIS_URL")
    redis_ready = _is_configured(redis_url)
    if redis_ready and redis_url:
        if runtime_checks:
            results.append(
                _check_redis_connectivity(
                    redis_url,
                    allow_memory_fallback=allow_memory_backend,
                )
            )
        else:
            results.append(CheckResult("session_backend", "PASS", "Redis session backend configured"))
    else:
        if allow_memory_backend:
            results.append(
                CheckResult(
                    "session_backend",
                    "WARN",
                    "REDIS_URL is not set; in-memory backend explicitly allowed",
                )
            )
        else:
            results.append(
                CheckResult(
                    "session_backend",
                    "WARN",
                    "REDIS_URL is not set; session store will be in-memory only",
                )
            )

    llm_configured = any(
        _is_configured(env.get(key)) for key in ("DASHSCOPE_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY")
    )
    if llm_configured:
        results.append(CheckResult("llm_provider", "PASS", "LLM provider credentials detected"))
    else:
        results.append(
            CheckResult(
                "llm_provider",
                "WARN",
                "No LLM key detected; output quality and city coverage may degrade",
            )
        )

    return results


def _http_request(
    method: str,
    url: str,
    headers: Mapping[str, str] | None = None,
    payload: Mapping[str, Any] | None = None,
    timeout: int = 60,
) -> tuple[int, Any]:
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)

    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = request.Request(url=url, method=method, data=body, headers=request_headers)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            status_code = int(resp.status)
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else None
            return status_code, parsed
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        parsed = None
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
        return int(exc.code), parsed


def run_api_smoke(base_url: str, env: Mapping[str, str], timeout: int = 60) -> list[CheckResult]:
    results: list[CheckResult] = []
    root = base_url.rstrip("/")
    api_headers: dict[str, str] = {}

    api_token = env.get("API_BEARER_TOKEN")
    if _is_configured(api_token):
        api_headers["Authorization"] = f"Bearer {api_token.strip()}"

    start_ms = int(time.time() * 1000)
    try:
        health_status, health_payload = _http_request("GET", f"{root}/health", timeout=timeout)
    except Exception as exc:
        results.append(CheckResult("health_endpoint", "FAIL", f"/health request failed: {exc}"))
    else:
        latency = int(time.time() * 1000) - start_ms
        if health_status == 200 and isinstance(health_payload, dict) and health_payload.get("status") == "ok":
            results.append(CheckResult("health_endpoint", "PASS", f"/health ok in {latency}ms"))
        else:
            results.append(
                CheckResult(
                    "health_endpoint",
                    "FAIL",
                    f"/health unexpected response: status={health_status}, payload={health_payload}",
                )
            )

    try:
        plan_status, plan_payload = _http_request(
            "POST",
            f"{root}/plan",
            headers=api_headers,
            payload={"message": "beijing 2 day trip"},
            timeout=timeout,
        )
    except Exception as exc:
        results.append(CheckResult("plan_endpoint", "FAIL", f"/plan request failed: {exc}"))
    else:
        if plan_status in {200, 422}:
            results.append(CheckResult("plan_endpoint", "PASS", f"/plan status={plan_status}"))
        else:
            results.append(
                CheckResult(
                    "plan_endpoint",
                    "FAIL",
                    f"/plan unexpected response: status={plan_status}, payload={plan_payload}",
                )
            )

    diagnostics_enabled = _is_enabled(env.get("ENABLE_DIAGNOSTICS"))
    diagnostics_token = env.get("DIAGNOSTICS_TOKEN")
    if diagnostics_enabled:
        headers = {}
        if _is_configured(diagnostics_token):
            headers["Authorization"] = f"Bearer {diagnostics_token.strip()}"
        try:
            diag_status, diag_payload = _http_request(
                "GET",
                f"{root}/diagnostics",
                headers=headers,
                timeout=timeout,
            )
        except Exception as exc:
            results.append(CheckResult("diagnostics_endpoint", "FAIL", f"/diagnostics failed: {exc}"))
        else:
            if diag_status == 200:
                results.append(CheckResult("diagnostics_endpoint", "PASS", "/diagnostics status=200"))
            else:
                results.append(
                    CheckResult(
                        "diagnostics_endpoint",
                        "FAIL",
                        f"/diagnostics unexpected response: status={diag_status}, payload={diag_payload}",
                    )
                )
    else:
        results.append(CheckResult("diagnostics_endpoint", "PASS", "Diagnostics endpoint is disabled"))

    return results


def _render_results(title: str, results: list[CheckResult]) -> None:
    print(f"== {title} ==")
    for item in results:
        print(f"[{item.status}] {item.name}: {item.detail}")
    print("")


def summarize(results: list[CheckResult]) -> tuple[int, int, int]:
    passed = sum(1 for item in results if item.status == "PASS")
    warned = sum(1 for item in results if item.status == "WARN")
    failed = sum(1 for item in results if item.status == "FAIL")
    return passed, warned, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="trip-agent pre-release checks")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend API base URL")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip HTTP smoke checks")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Optional env file to load before checks (default: .env)",
    )
    args = parser.parse_args()

    if args.env_file:
        load_dotenv(args.env_file, override=False)

    env_map = dict(os.environ)
    env_results = validate_environment(env_map, runtime_checks=True)
    all_results = list(env_results)
    _render_results("Environment Checks", env_results)

    if not args.skip_smoke:
        smoke_results = run_api_smoke(base_url=args.base_url, env=env_map, timeout=args.timeout)
        all_results.extend(smoke_results)
        _render_results("API Smoke Checks", smoke_results)

    passed, warned, failed = summarize(all_results)
    print(f"Summary: PASS={passed} WARN={warned} FAIL={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
