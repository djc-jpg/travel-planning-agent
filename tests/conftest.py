"""pytest 全局 fixtures — 测试环境隔离"""

import pytest


@pytest.fixture(autouse=True)
def no_real_apis(monkeypatch):
    """默认禁用真实 API（LLM + 高德），确保测试不依赖外部服务"""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED_API", "true")
    monkeypatch.delenv("DIAGNOSTICS_TOKEN", raising=False)
    monkeypatch.delenv("ENABLE_DIAGNOSTICS", raising=False)
    monkeypatch.delenv("STRICT_EXTERNAL_DATA", raising=False)
    # 重置 LLM 单例缓存，确保每个测试独立
    from app.infrastructure.llm_factory import reset_llm
    from app.security.key_manager import get_key_manager

    km = get_key_manager()
    for key_name in ("DASHSCOPE_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY", "AMAP_API_KEY"):
        km.reload(key_name)

    reset_llm()
    yield
    reset_llm()
