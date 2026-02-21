"""HTTP client timeout/retry cap tests."""

from __future__ import annotations

from app.security.http_client import SecureHttpClient


def test_http_client_applies_timeout_and_retry_caps(monkeypatch):
    monkeypatch.setenv("TOOL_HTTP_TIMEOUT_CAP_SECONDS", "5")
    monkeypatch.setenv("TOOL_HTTP_TIMEOUT_FLOOR_SECONDS", "1")
    monkeypatch.setenv("TOOL_HTTP_RETRY_CAP", "1")

    client = SecureHttpClient(timeout=30, max_retries=5, tool_name="test")
    assert client._timeout == 5.0
    assert client._max_retries == 1

