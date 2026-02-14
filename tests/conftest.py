"""pytest 全局 fixtures — 测试环境隔离"""

import pytest


@pytest.fixture(autouse=True)
def no_real_apis(monkeypatch):
    """默认禁用真实 API（LLM + 高德），确保测试不依赖外部服务"""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    # 重置 LLM 单例缓存，确保每个测试独立
    from app.infrastructure.llm_factory import reset_llm
    reset_llm()
    yield
    reset_llm()
