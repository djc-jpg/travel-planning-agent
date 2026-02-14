"""安全 HTTP 客户端 — 所有外部 API 调用的统一出口

职责：
  1. 自动脱敏异常中的 API Key
  2. 统一超时 / 重试策略
  3. 请求/响应日志（脱敏后）
  4. 隔离 httpx 依赖
"""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from app.security.key_manager import get_key_manager
from app.shared.exceptions import ToolError


class SecureHttpClient:
    """封装 httpx，自动脱敏异常及日志"""

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        max_retries: int = 1,
        tool_name: str = "http",
    ):
        self._timeout = timeout
        self._max_retries = max_retries
        self._tool_name = tool_name
        self._km = get_key_manager()

    def get(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """
        执行 GET 请求并返回 JSON。
        异常信息自动脱敏，不会泄露 Key。
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 2):
            try:
                resp = httpx.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                # 脱敏 HTTP 错误中可能包含的 URL（含 Key）
                safe_msg = self._km.scrub_text(str(e))
                last_error = ToolError(self._tool_name, f"HTTP {e.response.status_code}: {safe_msg}")
            except httpx.TimeoutException:
                last_error = ToolError(self._tool_name, f"请求超时（{self._timeout}s），第 {attempt} 次尝试")
            except httpx.HTTPError as e:
                safe_msg = self._km.scrub_text(str(e))
                last_error = ToolError(self._tool_name, f"网络请求失败: {safe_msg}")
            except Exception as e:
                safe_msg = self._km.scrub_text(str(e))
                last_error = ToolError(self._tool_name, f"未知错误: {safe_msg}")

            if attempt <= self._max_retries:
                time.sleep(0.5 * attempt)  # 简单退避

        raise last_error  # type: ignore[misc]

    def get_raw(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
    ) -> httpx.Response:
        """
        执行 GET 请求并返回原始 Response（非 JSON 场景）。
        异常信息自动脱敏。
        """
        try:
            resp = httpx.get(url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as e:
            safe_msg = self._km.scrub_text(str(e))
            raise ToolError(self._tool_name, f"请求失败: {safe_msg}") from None
