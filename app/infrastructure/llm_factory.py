"""LLM 工厂 — 根据环境变量决定是否启用 LLM

支持的环境变量（按优先级）：
  DASHSCOPE_API_KEY  → 阿里云通义千问（DashScope OpenAI 兼容端点）
  OPENAI_API_KEY     → OpenAI 原生
  LLM_API_KEY        → 自定义兼容端点（需配合 LLM_BASE_URL）

可选：
  LLM_MODEL    — 模型名，默认按供应商自动选择
  LLM_BASE_URL — 自定义 base_url
"""

from __future__ import annotations

import os
from typing import Optional

# DashScope OpenAI 兼容端点
_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DASHSCOPE_DEFAULT_MODEL = "qwen3-coder-plus"


def _resolve_config() -> tuple[str, str, str] | None:
    """
    返回 (api_key, base_url, model) 或 None。
    """
    # 1️⃣ 阿里云 DashScope
    ds_key = os.getenv("DASHSCOPE_API_KEY")
    if ds_key:
        return (
            ds_key,
            os.getenv("LLM_BASE_URL", _DASHSCOPE_BASE_URL),
            os.getenv("LLM_MODEL", _DASHSCOPE_DEFAULT_MODEL),
        )

    # 2️⃣ OpenAI 原生
    oai_key = os.getenv("OPENAI_API_KEY")
    if oai_key:
        return (
            oai_key,
            os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            os.getenv("LLM_MODEL", "gpt-4o-mini"),
        )

    # 3️⃣ 通用兼容端点
    llm_key = os.getenv("LLM_API_KEY")
    if llm_key:
        return (
            llm_key,
            os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            os.getenv("LLM_MODEL", "gpt-4o-mini"),
        )

    return None


# LLM 单次调用超时（秒）
_LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

# 模块级单例缓存
_llm_instance: Optional[object] = None
_llm_resolved: bool = False  # 区分 None（无 key）和未初始化


def get_llm() -> Optional[object]:
    """
    根据环境变量创建 LLM 实例（单例）。无 key 则返回 None（模板模式）。
    """
    global _llm_instance, _llm_resolved
    if _llm_resolved:
        return _llm_instance

    cfg = _resolve_config()
    if cfg is None:
        _llm_resolved = True
        _llm_instance = None
        return None

    api_key, base_url, model = cfg

    try:
        from langchain_openai import ChatOpenAI  # type: ignore

        _llm_instance = ChatOpenAI(
            model=model,
            temperature=0,
            api_key=api_key,
            base_url=base_url,
            timeout=_LLM_TIMEOUT,
            max_retries=1,
        )
    except ImportError:
        # langchain_openai 未安装，尝试用 openai 原生包装
        try:
            from openai import OpenAI  # type: ignore

            class _SimpleLLM:
                """最小 LLM 包装，兼容 .invoke(prompt) -> .content 接口"""

                def __init__(self):
                    self.client = OpenAI(
                        api_key=api_key,
                        base_url=base_url,
                        timeout=_LLM_TIMEOUT,
                        max_retries=1,
                    )
                    self.model = model

                def invoke(self, prompt: str):
                    resp = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0,
                    )

                    class _Msg:
                        def __init__(self, text: str):
                            self.content = text

                    return _Msg(resp.choices[0].message.content or "")

            _llm_instance = _SimpleLLM()
        except ImportError:
            _llm_instance = None

    _llm_resolved = True
    return _llm_instance


def reset_llm() -> None:
    """重置 LLM 单例（测试用）"""
    global _llm_instance, _llm_resolved
    _llm_instance = None
    _llm_resolved = False


def is_llm_available() -> bool:
    """检查是否有可用的 LLM 配置（不创建实例）"""
    return _resolve_config() is not None
