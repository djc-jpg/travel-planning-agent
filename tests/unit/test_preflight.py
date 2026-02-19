from app.deploy.preflight import validate_environment


def _as_map(results):
    return {item.name: item for item in results}


def test_api_auth_required_by_default():
    result_map = _as_map(validate_environment({}))
    assert result_map["api_auth"].status == "FAIL"


def test_allow_unauthenticated_api_downgrades_to_warn():
    result_map = _as_map(validate_environment({"ALLOW_UNAUTHENTICATED_API": "true"}))
    assert result_map["api_auth"].status == "WARN"


def test_diagnostics_requires_token_when_enabled():
    result_map = _as_map(validate_environment({"ENABLE_DIAGNOSTICS": "true"}))
    assert result_map["diagnostics_auth"].status == "FAIL"


def test_strict_external_data_requires_amap_key():
    result_map = _as_map(validate_environment({"STRICT_EXTERNAL_DATA": "true"}))
    assert result_map["strict_external_data"].status == "FAIL"


def test_cors_wildcard_with_credentials_is_fail():
    result_map = _as_map(
        validate_environment({"CORS_ORIGINS": "*", "CORS_ALLOW_CREDENTIALS": "true"})
    )
    assert result_map["cors_policy"].status == "FAIL"


def test_invalid_numeric_limits_are_fail():
    result_map = _as_map(validate_environment({"GRAPH_TIMEOUT_SECONDS": "0", "RATE_LIMIT_MAX": "-1"}))
    assert result_map["graph_timeout"].status == "FAIL"
    assert result_map["rate_limit"].status == "FAIL"


def test_configured_env_is_pass_for_critical_checks():
    env = {
        "API_BEARER_TOKEN": "api-secret",
        "ENABLE_DIAGNOSTICS": "true",
        "DIAGNOSTICS_TOKEN": "diag-secret",
        "STRICT_EXTERNAL_DATA": "true",
        "AMAP_API_KEY": "amap-secret",
        "CORS_ORIGINS": "http://localhost:3000",
        "CORS_ALLOW_CREDENTIALS": "false",
        "GRAPH_TIMEOUT_SECONDS": "120",
        "RATE_LIMIT_MAX": "60",
        "RATE_LIMIT_WINDOW": "60",
    }
    result_map = _as_map(validate_environment(env))
    assert result_map["api_auth"].status == "PASS"
    assert result_map["diagnostics_auth"].status == "PASS"
    assert result_map["strict_external_data"].status == "PASS"
    assert result_map["cors_policy"].status == "PASS"
    assert result_map["graph_timeout"].status == "PASS"
    assert result_map["rate_limit"].status == "PASS"


def test_redis_connectivity_runtime_check_can_fail(monkeypatch):
    def _fake_check(_url: str, allow_memory_fallback: bool = False):
        _ = allow_memory_fallback
        from app.deploy.preflight import CheckResult

        return CheckResult("session_backend", "FAIL", "redis unreachable")

    monkeypatch.setattr("app.deploy.preflight._check_redis_connectivity", _fake_check)
    result_map = _as_map(validate_environment({"REDIS_URL": "redis://redis:6379/0"}, runtime_checks=True))
    assert result_map["session_backend"].status == "FAIL"


def test_redis_unreachable_can_be_warn_when_memory_fallback_allowed(monkeypatch):
    def _fake_check(_url: str, allow_memory_fallback: bool = False):
        from app.deploy.preflight import CheckResult

        status = "WARN" if allow_memory_fallback else "FAIL"
        return CheckResult("session_backend", status, "redis unreachable")

    monkeypatch.setattr("app.deploy.preflight._check_redis_connectivity", _fake_check)
    result_map = _as_map(
        validate_environment(
            {"REDIS_URL": "redis://redis:6379/0", "ALLOW_INMEMORY_BACKEND": "true"},
            runtime_checks=True,
        )
    )
    assert result_map["session_backend"].status == "WARN"
