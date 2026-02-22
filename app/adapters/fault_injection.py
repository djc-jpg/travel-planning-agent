"""Optional tool fault injection for dependency drill scenarios.

Disabled by default. Enable by setting:
  ENABLE_TOOL_FAULT_INJECTION=true
  TOOL_FAULT_INJECTION=poi:timeout,route:rate_limit
  TOOL_FAULT_RATE=1.0
"""

from __future__ import annotations

import os
import random
from typing import Any

from app.shared.exceptions import ToolError

_TRUTHY = {"1", "true", "yes", "on"}
_SUPPORTED_FAULTS = {"timeout", "rate_limit", "unavailable"}


def _enabled() -> bool:
    return os.getenv("ENABLE_TOOL_FAULT_INJECTION", "false").strip().lower() in _TRUTHY


def _fault_rate() -> float:
    raw = os.getenv("TOOL_FAULT_RATE", "1.0").strip()
    try:
        value = float(raw)
    except ValueError:
        return 1.0
    return max(0.0, min(1.0, value))


def _fault_map() -> dict[str, str]:
    raw = os.getenv("TOOL_FAULT_INJECTION", "").strip()
    if not raw:
        return {}
    mapping: dict[str, str] = {}
    for part in raw.split(","):
        item = part.strip()
        if not item or ":" not in item:
            continue
        tool, fault = item.split(":", 1)
        tool_key = tool.strip().lower()
        fault_key = fault.strip().lower()
        if not tool_key or fault_key not in _SUPPORTED_FAULTS:
            continue
        mapping[tool_key] = fault_key
    return mapping


def _fault_for(tool_name: str) -> str:
    if not _enabled():
        return ""
    fault = _fault_map().get(tool_name.lower(), "")
    if not fault:
        return ""
    if random.random() > _fault_rate():
        return ""
    return fault


def _raise_fault(tool_name: str, fault: str, operation: str) -> None:
    op = f" op={operation}" if operation else ""
    if fault == "timeout":
        raise ToolError(tool_name, f"injected timeout{op}")
    if fault == "rate_limit":
        raise ToolError(tool_name, f"injected upstream rate limit 429{op}")
    if fault == "unavailable":
        raise ToolError(tool_name, f"injected upstream unavailable 503{op}")
    raise ToolError(tool_name, f"injected unknown fault {fault}{op}")


class FaultInjectedToolProxy:
    def __init__(self, tool_name: str, target: Any) -> None:
        self._tool_name = tool_name
        self._target = target

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr

        def _wrapped(*args: Any, **kwargs: Any):
            fault = _fault_for(self._tool_name)
            if fault:
                _raise_fault(self._tool_name, fault, name)
            return attr(*args, **kwargs)

        return _wrapped


def wrap_tool_with_fault_injection(tool_name: str, tool_impl: Any) -> Any:
    if not _enabled():
        return tool_impl
    return FaultInjectedToolProxy(tool_name, tool_impl)


__all__ = ["wrap_tool_with_fault_injection"]
