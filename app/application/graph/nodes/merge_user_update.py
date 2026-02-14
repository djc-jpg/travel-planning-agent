"""Merge User Update 节点 — 合并用户补充信息到 State

使用与 intake 相同的 LLM 优先 + 正则降级策略。
"""

from __future__ import annotations

from typing import Any

from app.application.graph.nodes.intake import _llm_extract
from app.parsing.regex_extractors import apply_llm_result, regex_extract
from app.parsing.requirements import check_missing


def merge_user_update_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    合并用户新消息中的信息到已有 constraints/profile，
    优先用 LLM 结构化提取，失败时降级到正则。
    """
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_msg = messages[-1].get("content", "") if isinstance(messages[-1], dict) else str(messages[-1])

    # 获取当前状态
    c = dict(state.get("trip_constraints", {}))
    if hasattr(c, "model_dump"):
        c = c.model_dump()
    p = dict(state.get("user_profile", {}))
    if hasattr(p, "model_dump"):
        p = p.model_dump()

    # LLM 优先，正则降级
    llm_result = _llm_extract(last_msg)
    if llm_result and isinstance(llm_result, dict):
        apply_llm_result(llm_result, c, p)
    else:
        regex_extract(last_msg, c, p)

    missing = check_missing(c, p)
    status = "clarifying" if missing else "planning"

    return {
        "trip_constraints": c,
        "user_profile": p,
        "requirements_missing": missing,
        "status": status,
    }
