from __future__ import annotations

from app.observability.prometheus_export import render_prometheus_metrics


def test_render_prometheus_metrics_contains_core_and_labeled_series():
    snapshot = {
        "total_requests": 12,
        "success_rate": 0.95,
        "p95_latency_ms": 1234.5,
        "llm_calls_per_request": 0.2,
        "status_counts": {"done": 10, "error": 2},
        "engine_counts": {"v1": 4, "v2": 8},
        "strict_required_fields": {"true": 3, "false": 9},
        "degrade_counts": {"L0": 2, "L1": 10},
        "tool_calls": {
            "poi.search": {
                "ok": 8,
                "error": 2,
                "latency": {"p95_ms": 88.8},
            }
        },
    }
    text = render_prometheus_metrics(snapshot)

    assert "trip_agent_requests_total" in text
    assert 'trip_agent_request_status_total{status="done"} 10.0' in text
    assert 'trip_agent_engine_requests_total{engine="v2"} 8.0' in text
    assert 'trip_agent_degrade_level_total{degrade_level="L1"} 10.0' in text
    assert 'trip_agent_tool_calls_total{status="ok",tool="poi.search"} 8.0' in text
    assert 'trip_agent_tool_latency_p95_ms{tool="poi.search"} 88.8' in text
