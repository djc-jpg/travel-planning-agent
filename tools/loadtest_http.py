"""HTTP load-test runner with capacity conclusion for 500+ concurrency targets."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import statistics
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

_DEFAULT_REPORT_DIR = Path("eval") / "reports"
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 18080
_DEFAULT_TIMEOUT_SECONDS = 30.0
_DEFAULT_TOTAL_REQUESTS = 1000
_DEFAULT_CONCURRENCY = 500
_DEFAULT_WARMUP_REQUESTS = 30
_DEFAULT_TARGET_SUCCESS_RATE = 0.99
_DEFAULT_TARGET_P95_MS = 3000.0
_DEFAULT_SPAWN_WORKERS = 1


@dataclass(frozen=True)
class LoadTestConfig:
    base_url: str
    endpoint: str
    total_requests: int
    concurrency: int
    warmup_requests: int
    timeout_seconds: float
    request_payload: dict[str, Any]
    auth_token: str
    target_success_rate: float
    target_p95_ms: float
    target_concurrency: int


@dataclass(frozen=True)
class RequestResult:
    ok: bool
    status_code: int
    latency_ms: float
    error: str


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    safe_ratio = max(0.0, min(1.0, ratio))
    idx = max(0, min(len(ordered) - 1, int((len(ordered) * safe_ratio) + 0.999999) - 1))
    return float(ordered[idx])


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_json_load(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON payload: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("request payload JSON must be an object")
    return value


def _capacity_conclusion(metrics: dict[str, Any], config: LoadTestConfig) -> dict[str, Any]:
    success_rate = float(metrics.get("success_rate", 0.0))
    p95_ms = float(metrics.get("p95_latency_ms", 0.0))
    observed_concurrency = int(metrics.get("concurrency", 0))
    meets_target = (
        observed_concurrency >= config.target_concurrency
        and success_rate >= config.target_success_rate
        and p95_ms <= config.target_p95_ms
    )

    reasons: list[str] = []
    if observed_concurrency < config.target_concurrency:
        reasons.append(f"concurrency {observed_concurrency} < target {config.target_concurrency}")
    if success_rate < config.target_success_rate:
        reasons.append(f"success_rate {success_rate:.4f} < target {config.target_success_rate:.4f}")
    if p95_ms > config.target_p95_ms:
        reasons.append(f"p95 {p95_ms:.2f}ms > target {config.target_p95_ms:.2f}ms")

    if meets_target:
        summary = (
            f"PASS: supports >= {config.target_concurrency} concurrency "
            f"(success_rate={success_rate:.4f}, p95={p95_ms:.2f}ms)."
        )
    else:
        summary = (
            f"FAIL: target not met at concurrency={observed_concurrency}; "
            + ("; ".join(reasons) if reasons else "see metrics for details")
        )
    return {
        "meets_target": meets_target,
        "target_concurrency": config.target_concurrency,
        "target_success_rate": config.target_success_rate,
        "target_p95_ms": config.target_p95_ms,
        "summary": summary,
        "reasons": reasons,
    }


def summarize_results(
    *,
    config: LoadTestConfig,
    started_at: float,
    completed_at: float,
    results: list[RequestResult],
) -> dict[str, Any]:
    latencies = [max(0.0, row.latency_ms) for row in results]
    status_counts = Counter(str(row.status_code) for row in results)
    error_counts = Counter(row.error for row in results if row.error)
    success_count = sum(1 for row in results if row.ok)
    success_rate = (success_count / max(len(results), 1)) if results else 0.0
    elapsed_seconds = max(0.001, completed_at - started_at)
    rps = len(results) / elapsed_seconds

    metrics = {
        "generated_at": _iso_now(),
        "base_url": config.base_url,
        "endpoint": config.endpoint,
        "concurrency": config.concurrency,
        "total_requests": config.total_requests,
        "warmup_requests": config.warmup_requests,
        "success_count": success_count,
        "error_count": max(0, len(results) - success_count),
        "success_rate": round(success_rate, 4),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "throughput_rps": round(rps, 2),
        "avg_latency_ms": round(statistics.fmean(latencies), 2) if latencies else 0.0,
        "p50_latency_ms": round(_percentile(latencies, 0.50), 2),
        "p95_latency_ms": round(_percentile(latencies, 0.95), 2),
        "p99_latency_ms": round(_percentile(latencies, 0.99), 2),
        "max_latency_ms": round(max(latencies), 2) if latencies else 0.0,
        "status_counts": dict(sorted(status_counts.items(), key=lambda item: item[0])),
        "error_counts": dict(sorted(error_counts.items(), key=lambda item: item[0])),
    }
    metrics["capacity_conclusion"] = _capacity_conclusion(metrics, config)
    return metrics


def render_markdown_report(report: dict[str, Any]) -> str:
    capacity = report.get("capacity_conclusion", {})
    status_counts = report.get("status_counts", {})
    error_counts = report.get("error_counts", {})
    lines = [
        "# Load Test Report",
        "",
        f"- generated_at: `{report.get('generated_at')}`",
        f"- base_url: `{report.get('base_url')}`",
        f"- endpoint: `{report.get('endpoint')}`",
        f"- concurrency: `{report.get('concurrency')}`",
        f"- total_requests: `{report.get('total_requests')}`",
        f"- success_rate: `{report.get('success_rate')}`",
        f"- p95_latency_ms: `{report.get('p95_latency_ms')}`",
        f"- throughput_rps: `{report.get('throughput_rps')}`",
        "",
        "## Capacity Conclusion",
        "",
        f"- meets_target: `{capacity.get('meets_target')}`",
        f"- summary: {capacity.get('summary', '')}",
    ]

    reasons = capacity.get("reasons", [])
    if isinstance(reasons, list) and reasons:
        lines.append("- reasons:")
        for reason in reasons:
            lines.append(f"  - {reason}")

    lines.extend(["", "## Status Counts", ""])
    if isinstance(status_counts, dict) and status_counts:
        for key, value in status_counts.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")

    lines.extend(["", "## Error Counts", ""])
    if isinstance(error_counts, dict) and error_counts:
        for key, value in error_counts.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


async def _wait_for_health(base_url: str, *, timeout_seconds: float, attempts: int = 40) -> None:
    target = base_url.rstrip("/") + "/health"
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        for _ in range(max(1, attempts)):
            try:
                resp = await client.get(target)
                if resp.status_code == 200:
                    return
            except Exception:
                pass
            await asyncio.sleep(0.3)
    raise RuntimeError(f"health check failed for {target}")


def _spawn_local_app(host: str, port: int, workers: int) -> subprocess.Popen[str]:
    env = dict(os.environ)
    env.setdefault("ALLOW_UNAUTHENTICATED_API", "true")
    env.setdefault("STRICT_EXTERNAL_DATA", "false")
    env.setdefault("ROUTING_PROVIDER", "fixture")
    env.setdefault("PLAN_PERSISTENCE_ENABLED", "false")
    env.setdefault("ENABLE_DIAGNOSTICS", "false")
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.api.main:app",
        "--host",
        host,
        "--port",
        str(port),
        "--workers",
        str(max(1, workers)),
    ]
    return subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _stop_process(proc: subprocess.Popen[str] | None) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=8)
    except Exception:
        try:
            proc.send_signal(signal.SIGKILL)
        except Exception:
            return


async def _run_single_request(
    *,
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> RequestResult:
    started = time.perf_counter()
    try:
        resp = await client.post(url, json=payload, headers=headers)
        latency_ms = (time.perf_counter() - started) * 1000.0
        ok = resp.status_code == 200
        if ok:
            return RequestResult(ok=True, status_code=resp.status_code, latency_ms=latency_ms, error="")
        detail = ""
        try:
            parsed = resp.json()
            if isinstance(parsed, dict):
                detail = str(parsed.get("detail", ""))
        except Exception:
            detail = resp.text.strip()[:120]
        return RequestResult(
            ok=False,
            status_code=resp.status_code,
            latency_ms=latency_ms,
            error=detail or f"http_{resp.status_code}",
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return RequestResult(ok=False, status_code=0, latency_ms=latency_ms, error=type(exc).__name__)


async def _run_burst(config: LoadTestConfig) -> list[RequestResult]:
    url = config.base_url.rstrip("/") + config.endpoint
    headers: dict[str, str] = {}
    if config.auth_token.strip():
        headers["Authorization"] = f"Bearer {config.auth_token.strip()}"

    limits = httpx.Limits(
        max_connections=max(config.concurrency * 2, 1000),
        max_keepalive_connections=max(config.concurrency, 500),
    )
    timeout = httpx.Timeout(
        timeout=config.timeout_seconds,
        connect=min(15.0, config.timeout_seconds),
        read=config.timeout_seconds,
        write=config.timeout_seconds,
        pool=config.timeout_seconds,
    )
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        if config.warmup_requests > 0:
            for _ in range(config.warmup_requests):
                await _run_single_request(
                    client=client,
                    url=url,
                    payload=config.request_payload,
                    headers=headers,
                )

        semaphore = asyncio.Semaphore(max(1, config.concurrency))
        rows: list[RequestResult] = []

        async def _worker() -> None:
            async with semaphore:
                row = await _run_single_request(
                    client=client,
                    url=url,
                    payload=config.request_payload,
                    headers=headers,
                )
                rows.append(row)

        tasks = [asyncio.create_task(_worker()) for _ in range(max(1, config.total_requests))]
        await asyncio.gather(*tasks)
        return rows


def _default_payload() -> dict[str, Any]:
    return {
        "message": "杭州2天轻松游，预算每天600，喜欢历史和美食",
        "constraints": {
            "city": "杭州",
            "days": 2,
            "date_start": "2026-04-01",
            "date_end": "2026-04-02",
            "budget_per_day": 600,
            "pace": "moderate",
        },
        "user_profile": {"themes": ["历史古迹", "美食夜市"], "travelers_type": "couple"},
        "metadata": {
            "source": "loadtest_http",
            "field_sources": {
                "city": "user_form",
                "days": "user_form",
                "date_start": "user_form",
                "date_end": "user_form",
            },
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run 500+ concurrency HTTP load test with capacity verdict")
    parser.add_argument("--base-url", default=f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}")
    parser.add_argument("--endpoint", default="/plan")
    parser.add_argument("--total-requests", type=int, default=_DEFAULT_TOTAL_REQUESTS)
    parser.add_argument("--concurrency", type=int, default=_DEFAULT_CONCURRENCY)
    parser.add_argument("--warmup-requests", type=int, default=_DEFAULT_WARMUP_REQUESTS)
    parser.add_argument("--timeout-seconds", type=float, default=_DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--auth-token", default="")
    parser.add_argument("--request-payload", default="")
    parser.add_argument("--target-success-rate", type=float, default=_DEFAULT_TARGET_SUCCESS_RATE)
    parser.add_argument("--target-p95-ms", type=float, default=_DEFAULT_TARGET_P95_MS)
    parser.add_argument("--target-concurrency", type=int, default=_DEFAULT_CONCURRENCY)
    parser.add_argument("--report-dir", default=str(_DEFAULT_REPORT_DIR))
    parser.add_argument("--spawn-app", action="store_true", help="spawn local uvicorn app for the test")
    parser.add_argument("--spawn-host", default=_DEFAULT_HOST)
    parser.add_argument("--spawn-port", type=int, default=_DEFAULT_PORT)
    parser.add_argument("--spawn-workers", type=int, default=_DEFAULT_SPAWN_WORKERS)
    return parser


def _build_config(args: argparse.Namespace) -> LoadTestConfig:
    payload = _default_payload()
    raw_payload = str(args.request_payload).strip()
    if raw_payload:
        payload = _safe_json_load(raw_payload)

    base_url = str(args.base_url).strip().rstrip("/")
    if not base_url:
        raise ValueError("base-url must not be empty")

    endpoint = str(args.endpoint).strip()
    if not endpoint.startswith("/"):
        raise ValueError("endpoint must start with '/'")

    return LoadTestConfig(
        base_url=base_url,
        endpoint=endpoint,
        total_requests=max(1, int(args.total_requests)),
        concurrency=max(1, int(args.concurrency)),
        warmup_requests=max(0, int(args.warmup_requests)),
        timeout_seconds=max(1.0, float(args.timeout_seconds)),
        request_payload=payload,
        auth_token=str(args.auth_token),
        target_success_rate=max(0.0, min(1.0, float(args.target_success_rate))),
        target_p95_ms=max(1.0, float(args.target_p95_ms)),
        target_concurrency=max(1, int(args.target_concurrency)),
    )


def _write_reports(*, report: dict[str, Any], report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = report_dir / f"loadtest_{stamp}.json"
    md_path = report_dir / f"loadtest_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    return json_path, md_path


async def _run_main_async(args: argparse.Namespace) -> int:
    process: subprocess.Popen[str] | None = None
    config = _build_config(args)

    if args.spawn_app:
        process = _spawn_local_app(
            str(args.spawn_host),
            int(args.spawn_port),
            int(args.spawn_workers),
        )
        config = LoadTestConfig(
            **{
                **config.__dict__,
                "base_url": f"http://{str(args.spawn_host)}:{int(args.spawn_port)}",
            }
        )
        await _wait_for_health(config.base_url, timeout_seconds=config.timeout_seconds)
    else:
        await _wait_for_health(config.base_url, timeout_seconds=config.timeout_seconds)

    started = time.perf_counter()
    try:
        rows = await _run_burst(config)
    finally:
        _stop_process(process)
    completed = time.perf_counter()

    report = summarize_results(
        config=config,
        started_at=started,
        completed_at=completed,
        results=rows,
    )
    report["spawn_app"] = bool(args.spawn_app)
    report["spawn_workers"] = max(1, int(args.spawn_workers))

    json_path, md_path = _write_reports(report=report, report_dir=Path(str(args.report_dir)))

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report_json={json_path}")
    print(f"report_md={md_path}")
    return 0 if bool(report.get("capacity_conclusion", {}).get("meets_target")) else 2


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
