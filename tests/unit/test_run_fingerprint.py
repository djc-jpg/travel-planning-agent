"""Run fingerprint builder tests."""

from __future__ import annotations

from app.config.runtime_fingerprint import RunMode, build_run_fingerprint


def _clear_provider_env(monkeypatch) -> None:
    for key in (
        "AMAP_API_KEY",
        "DASHSCOPE_API_KEY",
        "OPENAI_API_KEY",
        "LLM_API_KEY",
        "ROUTING_PROVIDER",
        "STRICT_EXTERNAL_DATA",
        "ENV_SOURCE",
        "APP_ENV_SOURCE",
        "ENV_FILE",
        "DOTENV_FILE",
        "REDIS_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_build_run_fingerprint_defaults_to_degraded(monkeypatch):
    _clear_provider_env(monkeypatch)

    fp = build_run_fingerprint(trace_id="trace_a")

    assert fp.run_mode == RunMode.DEGRADED
    assert fp.poi_provider == "mock"
    assert fp.route_provider == "fixture"
    assert fp.llm_provider == "template"
    assert fp.strict_external_data is False
    assert fp.trace_id == "trace_a"


def test_build_run_fingerprint_is_realtime_with_real_providers(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("AMAP_API_KEY", "amap-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setenv("ROUTING_PROVIDER", "real")
    monkeypatch.setenv("STRICT_EXTERNAL_DATA", "true")

    fp = build_run_fingerprint(trace_id="trace_b")

    assert fp.run_mode == RunMode.REALTIME
    assert fp.poi_provider == "amap"
    assert fp.route_provider == "real"
    assert fp.llm_provider == "dashscope"
    assert fp.strict_external_data is True


def test_build_run_fingerprint_prefers_real_route_when_amap_key_exists(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("AMAP_API_KEY", "amap-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")

    fp = build_run_fingerprint(trace_id="trace_auto")

    assert fp.run_mode == RunMode.REALTIME
    assert fp.route_provider == "real"


def test_build_run_fingerprint_marks_runtime_fallback(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("AMAP_API_KEY", "amap-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setenv("ROUTING_PROVIDER", "real")

    fp = build_run_fingerprint(
        trace_id="trace_c",
        itinerary={"routing_source": "fallback_fixture"},
    )

    assert fp.run_mode == RunMode.DEGRADED
    assert fp.route_provider == "fallback_fixture"


def test_build_run_fingerprint_prefers_explicit_env_source(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("ENV_SOURCE", "manual-env")

    fp = build_run_fingerprint(trace_id="trace_d")

    assert fp.env_source == "manual-env"


def test_build_run_fingerprint_accepts_llm_compatible_as_realtime(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("AMAP_API_KEY", "amap-key")
    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    monkeypatch.setenv("ROUTING_PROVIDER", "real")

    fp = build_run_fingerprint(trace_id="trace_e")

    assert fp.llm_provider == "llm_compatible"
    assert fp.run_mode == RunMode.REALTIME
