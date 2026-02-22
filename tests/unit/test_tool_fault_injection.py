from __future__ import annotations

import pytest

from app.adapters.fault_injection import wrap_tool_with_fault_injection
from app.shared.exceptions import ToolError


class _Tool:
    def __init__(self) -> None:
        self.called = 0

    def run(self) -> str:
        self.called += 1
        return "ok"


def test_fault_injection_disabled_keeps_original_behavior(monkeypatch):
    monkeypatch.setenv("ENABLE_TOOL_FAULT_INJECTION", "false")
    tool = _Tool()
    wrapped = wrap_tool_with_fault_injection("poi", tool)
    assert wrapped.run() == "ok"
    assert tool.called == 1


@pytest.mark.parametrize("fault", ["timeout", "rate_limit", "unavailable"])
def test_fault_injection_raises_tool_error(monkeypatch, fault: str):
    monkeypatch.setenv("ENABLE_TOOL_FAULT_INJECTION", "true")
    monkeypatch.setenv("TOOL_FAULT_INJECTION", f"poi:{fault}")
    monkeypatch.setenv("TOOL_FAULT_RATE", "1.0")
    tool = _Tool()
    wrapped = wrap_tool_with_fault_injection("poi", tool)

    with pytest.raises(ToolError):
        wrapped.run()
