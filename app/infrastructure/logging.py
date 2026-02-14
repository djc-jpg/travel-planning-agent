"""结构化日志 — JSON line 格式，支持敏感信息脱敏"""

from __future__ import annotations

import json
import sys
import time
import uuid
from typing import Any, Optional


def _get_scrubber():
    """延迟导入 KeyManager 避免循环依赖"""
    try:
        from app.security.key_manager import get_key_manager
        return get_key_manager()
    except Exception:
        return None


class StructuredLogger:
    """结构化日志器，输出 JSON line，自动脱敏敏感信息。"""

    def __init__(self, trace_id: Optional[str] = None, output=None):
        self.trace_id = trace_id or str(uuid.uuid4())[:8]
        self._output = output or sys.stderr
        self._timers: dict[str, float] = {}

    def _scrub(self, text: str) -> str:
        """对文本中的敏感信息做脱敏"""
        km = _get_scrubber()
        if km:
            return km.scrub_text(text)
        return text

    def _emit(self, data: dict[str, Any]) -> None:
        data["trace_id"] = self.trace_id
        data["timestamp"] = time.time()
        try:
            # 序列化后做全局脱敏
            line = json.dumps(data, ensure_ascii=False, default=str)
            line = self._scrub(line)
            self._output.write(line + "\n")
            self._output.flush()
        except Exception as exc:
            # Last-resort fallback to avoid silent logger failures.
            try:
                fallback = {
                    "event": "logger_internal_error",
                    "trace_id": self.trace_id,
                    "timestamp": time.time(),
                    "error": str(exc),
                }
                sys.stderr.write(json.dumps(fallback, ensure_ascii=False, default=str) + "\n")
                sys.stderr.flush()
            except Exception:
                return

    def node_start(self, node_name: str, **extra: Any) -> None:
        self._timers[node_name] = time.time()
        self._emit({"event": "node_start", "node": node_name, **extra})

    def node_end(
        self,
        node_name: str,
        *,
        repair_attempts: int = 0,
        issues_count: int = 0,
        **extra: Any,
    ) -> None:
        start = self._timers.pop(node_name, time.time())
        duration_ms = round((time.time() - start) * 1000, 1)
        self._emit({
            "event": "node_end",
            "node": node_name,
            "duration_ms": duration_ms,
            "repair_attempts": repair_attempts,
            "issues_count": issues_count,
            **extra,
        })

    def tool_call(self, tool_name: str, **extra: Any) -> None:
        self._emit({"event": "tool_call", "tool": tool_name, **extra})

    def error(self, node_name: str, error: str, **extra: Any) -> None:
        # 对错误信息做脱敏
        safe_error = self._scrub(error)
        self._emit({"event": "error", "node": node_name, "error": safe_error, **extra})

    def warning(self, node_name: str, message: str, **extra: Any) -> None:
        safe_msg = self._scrub(message)
        self._emit({"event": "warning", "node": node_name, "message": safe_msg, **extra})

    def summary(self, **extra: Any) -> None:
        self._emit({"event": "summary", **extra})


# 全局 logger
_logger: Optional[StructuredLogger] = None


def get_logger(trace_id: Optional[str] = None) -> StructuredLogger:
    global _logger
    if _logger is None or (trace_id and _logger.trace_id != trace_id):
        _logger = StructuredLogger(trace_id=trace_id)
    return _logger
