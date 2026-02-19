"""集中式 API Key 管理器

职责：
  1. 统一管理所有 API Key 的读取与缓存
  2. 提供 Key 脱敏方法（用于日志/异常）
  3. 密钥轮换支持（预留）
  4. 密钥审计日志

所有外部 API 调用应通过此模块获取 Key，禁止直接 os.getenv。
"""

from __future__ import annotations

import os
import time
from typing import Optional

from app.security.redact import redact_sensitive
from app.shared.exceptions import KeyMissingError

class _KeyEntry:
    """单个 Key 的元数据"""

    __slots__ = ("value", "loaded_at", "source")

    def __init__(self, value: str, source: str):
        self.value = value
        self.loaded_at = time.time()
        self.source = source  # "env" / "vault" / ...


class KeyManager:
    """全局单例 Key 管理器"""

    def __init__(self):
        self._keys: dict[str, _KeyEntry] = {}
        self._access_log: list[dict] = []  # 审计用

    # ── 读取 ──────────────────────────────────────────

    def get(self, name: str, *, required: bool = False) -> Optional[str]:
        """
        获取指定名称的 Key。
        优先从缓存读取，否则从环境变量加载。
        """
        entry = self._keys.get(name)
        if entry is None:
            raw = os.getenv(name, "")
            if raw:
                entry = _KeyEntry(value=raw, source="env")
                self._keys[name] = entry
            elif required:
                raise KeyMissingError(name)
            else:
                return None

        self._access_log.append({
            "key": name,
            "time": time.time(),
            "source": entry.source,
        })
        return entry.value

    def get_amap_key(self, *, required: bool = True) -> str:
        """获取高德 API Key"""
        val = self.get("AMAP_API_KEY", required=required)
        return val or ""

    def get_amap_secret(self) -> Optional[str]:
        """获取高德数字签名 Secret（可选）"""
        return self.get("AMAP_SECRET")

    def get_llm_key(self) -> Optional[str]:
        """获取 LLM Key（按优先级尝试）"""
        for name in ("DASHSCOPE_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"):
            val = self.get(name)
            if val:
                return val
        return None

    # ── 脱敏 ──────────────────────────────────────────

    @staticmethod
    def redact(value: str) -> str:
        """对 Key 做脱敏：仅保留前 4 和后 4 位"""
        if not value or len(value) <= 8:
            return "****"
        return value[:4] + "****" + value[-4:]

    def redact_name(self, name: str) -> str:
        """对指定名称的 Key 进行脱敏"""
        entry = self._keys.get(name)
        if entry is None:
            return "****"
        return self.redact(entry.value)

    def scrub_text(self, text: str) -> str:
        """
        从任意文本中擦除所有已知 Key 值。
        用于日志/异常消息安全输出。
        """
        result = str(text) if text is not None else ""
        for name, entry in self._keys.items():
            if entry.value and entry.value in result:
                result = result.replace(entry.value, f"[{name}:***REDACTED***]")
        return redact_sensitive(result)

    # ── 审计 ──────────────────────────────────────────

    def get_access_log(self, last_n: int = 100) -> list[dict]:
        """获取最近 N 条 Key 访问记录"""
        return self._access_log[-last_n:]

    def has_key(self, name: str) -> bool:
        """检查指定 Key 是否存在（不触发审计日志）"""
        if name in self._keys:
            return True
        return bool(os.getenv(name, ""))

    # ── 重新加载（用于密钥轮换） ──────────────────────

    def reload(self, name: str) -> None:
        """强制从环境变量重新加载指定 Key"""
        raw = os.getenv(name, "")
        if raw:
            self._keys[name] = _KeyEntry(value=raw, source="env")
        elif name in self._keys:
            del self._keys[name]


# ── 全局单例 ──────────────────────────────────────────

_manager: Optional[KeyManager] = None


def get_key_manager() -> KeyManager:
    global _manager
    if _manager is None:
        _manager = KeyManager()
    return _manager
