from __future__ import annotations

from tools.loadtest_http import (
    LoadTestConfig,
    RequestResult,
    _capacity_conclusion,
    _percentile,
    summarize_results,
)


def _config() -> LoadTestConfig:
    return LoadTestConfig(
        base_url="http://127.0.0.1:8000",
        endpoint="/plan",
        total_requests=1000,
        concurrency=500,
        warmup_requests=30,
        timeout_seconds=30.0,
        request_payload={"message": "x"},
        auth_token="",
        target_success_rate=0.99,
        target_p95_ms=3000.0,
        target_concurrency=500,
    )


def test_percentile_handles_empty_and_common_ratios():
    assert _percentile([], 0.95) == 0.0
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert _percentile(values, 0.50) == 30.0
    assert _percentile(values, 0.95) == 50.0


def test_capacity_conclusion_passes_when_targets_met():
    config = _config()
    metrics = {
        "concurrency": 500,
        "success_rate": 0.995,
        "p95_latency_ms": 1200.0,
    }
    result = _capacity_conclusion(metrics, config)
    assert result["meets_target"] is True
    assert "PASS" in result["summary"]
    assert result["reasons"] == []


def test_capacity_conclusion_fails_when_success_and_latency_below_target():
    config = _config()
    metrics = {
        "concurrency": 500,
        "success_rate": 0.97,
        "p95_latency_ms": 3500.0,
    }
    result = _capacity_conclusion(metrics, config)
    assert result["meets_target"] is False
    assert any("success_rate" in reason for reason in result["reasons"])
    assert any("p95" in reason for reason in result["reasons"])


def test_summarize_results_aggregates_status_and_errors():
    config = _config()
    rows = [
        RequestResult(ok=True, status_code=200, latency_ms=100.0, error=""),
        RequestResult(ok=True, status_code=200, latency_ms=120.0, error=""),
        RequestResult(ok=False, status_code=429, latency_ms=300.0, error="rate_limited"),
        RequestResult(ok=False, status_code=0, latency_ms=20.0, error="ConnectError"),
    ]
    report = summarize_results(
        config=config,
        started_at=10.0,
        completed_at=12.0,
        results=rows,
    )

    assert report["total_requests"] == 1000
    assert report["success_count"] == 2
    assert report["error_count"] == 2
    assert report["status_counts"]["200"] == 2
    assert report["status_counts"]["429"] == 1
    assert report["status_counts"]["0"] == 1
    assert report["error_counts"]["rate_limited"] == 1
    assert report["error_counts"]["ConnectError"] == 1
