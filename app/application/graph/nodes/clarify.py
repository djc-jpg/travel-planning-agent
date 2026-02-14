"""Clarify 节点 — 根据 requirements_missing 生成追问文本"""

from __future__ import annotations

from typing import Any

from app.parsing.requirements import FIELD_LABELS


def _llm_clarify(missing: list[str], user_msg: str) -> str | None:
    """用 LLM 生成自然、友好的追问话术"""
    try:
        from app.infrastructure.llm_factory import get_llm

        llm = get_llm()
        if llm is None:
            return None

        fields_zh = [FIELD_LABELS.get(f, f) for f in missing]
        prompt = (
            "你是一位热情友好的旅行顾问，用户发来了旅行需求但信息不完整。\n"
            "请用轻松亲切的口吻向用户追问缺失信息，让对话自然流畅。\n"
            "要求：1)不要列编号 2)用口语化表达 3)可以给出建议选项 4)控制在100字以内\n\n"
            f"用户说：{user_msg}\n"
            f"缺失信息：{'、'.join(fields_zh)}\n\n"
            "请直接输出追问话术："
        )
        resp = llm.invoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)
        return content.strip()
    except Exception:
        return None


def clarify_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Clarify 节点：若有缺参，生成追问消息并保持 clarifying 状态。
    有 LLM 时生成自然语言追问，否则用模板。
    """
    missing = state.get("requirements_missing", [])
    if not missing:
        return {"status": "planning"}

    # 获取用户原始消息
    msgs = state.get("messages", [])
    user_msg = ""
    if msgs:
        last = msgs[-1]
        user_msg = last.get("content", "") if isinstance(last, dict) else str(last)

    # 尝试 LLM 生成
    question = _llm_clarify(missing, user_msg)

    # 降级到模板
    if not question:
        fields_zh = [FIELD_LABELS.get(f, f) for f in missing]
        question = "为了帮你规划行程，还需要确认以下信息：\n"
        for i, label in enumerate(fields_zh, 1):
            question += f"  {i}. {label}\n"
        question += "请补充以上信息～"

    messages = list(msgs)
    messages.append({"role": "assistant", "content": question})

    return {
        "messages": messages,
        "status": "clarifying",
    }
