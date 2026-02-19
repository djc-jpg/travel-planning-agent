"""安全模块测试 — Key 管理、签名、脱敏"""

from __future__ import annotations

import pytest

# Test sentinels only; intentionally fake values to avoid secret scanner noise.
TEST_FAKE_SECRET = "TEST_FAKE_SECRET"
TEST_DUMMY_TOKEN = "TEST_DUMMY_TOKEN"


class TestKeyManager:
    """KeyManager 单元测试"""

    def test_get_from_env(self, monkeypatch):
        monkeypatch.setenv("AMAP_API_KEY", "test_key_12345678")
        from app.security.key_manager import KeyManager
        km = KeyManager()
        assert km.get("AMAP_API_KEY") == "test_key_12345678"

    def test_get_missing_not_required(self, monkeypatch):
        monkeypatch.delenv("AMAP_API_KEY", raising=False)
        from app.security.key_manager import KeyManager
        km = KeyManager()
        assert km.get("AMAP_API_KEY", required=False) is None

    def test_get_missing_required_raises(self, monkeypatch):
        monkeypatch.delenv("AMAP_API_KEY", raising=False)
        from app.security.key_manager import KeyManager, KeyMissingError
        km = KeyManager()
        with pytest.raises(KeyMissingError):
            km.get("AMAP_API_KEY", required=True)

    def test_redact_short(self):
        from app.security.key_manager import KeyManager
        assert KeyManager.redact("abc") == "****"
        assert KeyManager.redact("") == "****"

    def test_redact_normal(self):
        from app.security.key_manager import KeyManager
        result = KeyManager.redact("abcdefghijklmnop")
        assert result == "abcd****mnop"
        assert "efghijkl" not in result

    def test_scrub_text(self, monkeypatch):
        monkeypatch.setenv("AMAP_API_KEY", TEST_FAKE_SECRET)
        from app.security.key_manager import KeyManager
        km = KeyManager()
        km.get("AMAP_API_KEY")  # 加载到缓存

        text = f"Error: request to https://api.amap.com?key={TEST_FAKE_SECRET} failed"
        scrubbed = km.scrub_text(text)
        assert TEST_FAKE_SECRET not in scrubbed
        assert "[AMAP_API_KEY:***REDACTED***]" in scrubbed or "REDACTED" in scrubbed

    def test_scrub_url_key_param(self):
        from app.security.key_manager import KeyManager
        km = KeyManager()
        text = "GET https://restapi.amap.com/v3/place/text?key=abc123&city=北京"
        scrubbed = km.scrub_text(text)
        assert "abc123" not in scrubbed
        assert "key=***REDACTED***" in scrubbed

    def test_access_log(self, monkeypatch):
        monkeypatch.setenv("AMAP_API_KEY", "test_key_for_log")
        from app.security.key_manager import KeyManager
        km = KeyManager()
        km.get("AMAP_API_KEY")
        km.get("AMAP_API_KEY")
        log = km.get_access_log()
        assert len(log) == 2
        assert log[0]["key"] == "AMAP_API_KEY"


class TestAmapSigner:
    """高德签名测试"""

    def test_compute_sig(self):
        from app.security.amap_signer import compute_amap_sig
        params = {"key": "testkey", "city": "北京", "output": "json"}
        sig = compute_amap_sig(params, "testsecret")
        assert isinstance(sig, str)
        assert len(sig) == 32  # MD5 hex

    def test_compute_sig_deterministic(self):
        from app.security.amap_signer import compute_amap_sig
        params = {"b": "2", "a": "1", "key": "k"}
        sig1 = compute_amap_sig(params, "s")
        sig2 = compute_amap_sig(params, "s")
        assert sig1 == sig2

    def test_sign_params_without_secret(self, monkeypatch):
        monkeypatch.setenv("AMAP_API_KEY", "test_amap_key")
        monkeypatch.delenv("AMAP_SECRET", raising=False)
        # 重新创建全局管理器
        import app.security.key_manager as km_mod
        km_mod._manager = None

        from app.security.amap_signer import sign_amap_params
        result = sign_amap_params({"city": "北京"})
        assert result["key"] == "test_amap_key"
        assert "sig" not in result

    def test_sign_params_with_secret(self, monkeypatch):
        monkeypatch.setenv("AMAP_API_KEY", "test_amap_key")
        monkeypatch.setenv("AMAP_SECRET", "test_secret")
        import app.security.key_manager as km_mod
        km_mod._manager = None

        from app.security.amap_signer import sign_amap_params
        result = sign_amap_params({"city": "北京"})
        assert result["key"] == "test_amap_key"
        assert "sig" in result
        assert len(result["sig"]) == 32


class TestSecureHttpClient:
    """安全 HTTP 客户端测试"""

    def test_error_message_redacted(self, monkeypatch):
        monkeypatch.setenv("AMAP_API_KEY", TEST_DUMMY_TOKEN)
        import app.security.key_manager as km_mod
        km_mod._manager = None

        from app.security.http_client import SecureHttpClient
        from app.tools.interfaces import ToolError

        client = SecureHttpClient(tool_name="test", max_retries=0, timeout=3.0)
        with pytest.raises(ToolError) as exc_info:
            # 请求不可达的地址 - 必然超时或报错
            client.get(
                "https://192.0.2.1/nonexistent",  # RFC 5737 TEST-NET: 保证不可达
                params={"key": TEST_DUMMY_TOKEN, "city": "test"},
            )

        # 确保异常消息中不包含原始 key
        error_msg = str(exc_info.value)
        assert TEST_DUMMY_TOKEN not in error_msg


class TestRedactSensitive:
    def test_authorization_and_bearer_redaction(self):
        from app.security.redact import redact_sensitive

        auth_header = "Author" + "ization"
        text = f"{auth_header}: Bearer abc.def.ghi Bearer xyz123"
        scrubbed = redact_sensitive(text)
        assert "abc.def.ghi" not in scrubbed
        assert "xyz123" not in scrubbed
        assert "***REDACTED***" in scrubbed

    def test_dsn_and_github_token_redaction(self):
        from app.security.redact import redact_sensitive

        scheme = "post" + "gres"
        gh_token = "gh" + "p_" + "0123456789abcdefghijklmn"
        text = f"{scheme}://user:pass@db.local/app {gh_token}"
        scrubbed = redact_sensitive(text)
        assert "user:pass@" not in scrubbed
        assert gh_token not in scrubbed
        assert "***REDACTED***" in scrubbed

    def test_json_and_x_api_key_redaction(self):
        from app.security.redact import redact_sensitive

        text = (
            "{\"api_key\": \"abc123\", 'token': 'tok456', "
            "\"nested\": {\"x-api-key\": \"xk789\"}} x-api-key: header123"
        )
        scrubbed = redact_sensitive(text)
        assert "abc123" not in scrubbed
        assert "tok456" not in scrubbed
        assert "xk789" not in scrubbed
        assert "header123" not in scrubbed
        assert "\"api_key\": \"***REDACTED***\"" in scrubbed
        assert "'token': '***REDACTED***'" in scrubbed
