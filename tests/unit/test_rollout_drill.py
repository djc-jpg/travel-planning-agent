"""Unit tests for rollout drill smoke logic."""

from __future__ import annotations

from app.deploy import rollout_drill


def test_rollout_drill_passes_when_strict_behavior_matches(monkeypatch):
    calls = []

    def _fake_http(method, url, headers=None, payload=None, timeout=60):
        calls.append((method, url, payload))
        if url.endswith("/health"):
            return 200, {"status": "ok"}
        if url.endswith("/plan") and payload and "constraints" in payload:
            return 200, {"status": "done"}
        if url.endswith("/plan"):
            return 200, {"status": "clarifying"}
        if url.endswith("/diagnostics"):
            return 200, {
                "runtime_flags": {
                    "engine_version": "v2",
                    "strict_required_fields": True,
                }
            }
        return 500, {}

    monkeypatch.setattr(rollout_drill, "_http_request", _fake_http)

    results = rollout_drill.run_rollout_drill(
        base_url="http://127.0.0.1:8000",
        env={
            "API_BEARER_TOKEN": "api-token",
            "ENABLE_DIAGNOSTICS": "true",
            "DIAGNOSTICS_TOKEN": "diag-token",
        },
        expect_engine="v2",
        expect_strict=True,
    )

    assert all(item.status in {"PASS", "WARN"} for item in results)
    assert any(item.name == "missing_fields_behavior" and item.status == "PASS" for item in results)
    assert any(item.name == "diagnostics_flags" and item.status == "PASS" for item in results)


def test_rollout_drill_fails_when_strict_behavior_does_not_match(monkeypatch):
    def _fake_http(method, url, headers=None, payload=None, timeout=60):
        _ = method, headers, timeout
        if url.endswith("/health"):
            return 200, {"status": "ok"}
        if url.endswith("/plan") and payload and "constraints" in payload:
            return 200, {"status": "done"}
        if url.endswith("/plan"):
            return 200, {"status": "done"}
        return 404, {}

    monkeypatch.setattr(rollout_drill, "_http_request", _fake_http)

    results = rollout_drill.run_rollout_drill(
        base_url="http://127.0.0.1:8000",
        env={},
        expect_engine="v2",
        expect_strict=True,
    )

    assert any(item.name == "missing_fields_behavior" and item.status == "FAIL" for item in results)

