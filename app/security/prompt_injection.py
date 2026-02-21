"""Baseline prompt-injection detector."""

from __future__ import annotations

import re

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ignore_instructions", re.compile(r"(?i)\b(ignore|forget)\b.{0,40}\b(instruction|rule|system)\b")),
    ("reveal_prompt", re.compile(r"(?i)\b(system prompt|developer prompt|hidden prompt)\b")),
    ("reveal_secret", re.compile(r"(?i)\b(api[_ -]?key|token|secret|password|credential)\b")),
    ("tool_escape", re.compile(r"(?i)\b(shell|terminal|execute|run)\b.{0,40}\b(command|curl|powershell|bash)\b")),
    ("jailbreak", re.compile(r"(?i)(jailbreak|DAN|越狱|忽略以上|忽略之前)")),
)


def detect_prompt_injection(text: str) -> list[str]:
    if not text:
        return []
    content = str(text)
    hits: list[str] = []
    for name, pattern in _PATTERNS:
        if pattern.search(content):
            hits.append(name)
    return hits


__all__ = ["detect_prompt_injection"]
