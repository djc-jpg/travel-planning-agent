"""Intake 节点 — 从用户消息中抽取 TripConstraints / UserProfile"""

from __future__ import annotations

import os
from typing import Any

from app.parsing.regex_extractors import (
    KNOWN_CITIES,
    PACE_MAP,
    THEME_KEYWORDS,
    TRANSPORT_MAP,
    TRAVELERS_MAP,
    apply_llm_result,
    apply_text_evidence,
    extract_budget,
    extract_city,
    extract_days,
    regex_extract,
)
from app.parsing.requirements import check_missing

# ── 向后兼容：旧名称别名（已弃用，请使用 app.agent.utils） ──
_KNOWN_CITIES = KNOWN_CITIES
_PACE_MAP = PACE_MAP
_TRANSPORT_MAP = TRANSPORT_MAP
_TRAVELERS_MAP = TRAVELERS_MAP
_THEME_KEYWORDS = THEME_KEYWORDS
_extract_city = extract_city
_extract_days = extract_days
_extract_budget = extract_budget


def _is_enabled(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _use_llm_extract() -> bool:
    # In strict external mode we default to deterministic extraction for latency stability.
    strict_external = _is_enabled("STRICT_EXTERNAL_DATA", default=False)
    return _is_enabled("INTAKE_LLM_ENABLED", default=not strict_external)


def _llm_extract(text: str) -> dict | None:
    """
    尝试用 LLM 从用户消息中结构化提取旅行约束。
    成功返回 dict，失败返回 None（降级到正则）。
    """
    try:
        import json as _json

        from app.infrastructure.llm_factory import get_llm

        llm = get_llm()
        if llm is None:
            return None

        prompt = (
            "你是旅行助手。请从用户消息中提取旅行信息，返回 JSON（只返回 JSON，无其他文字）。\n"
            "字段说明：\n"
            "- city: 目的地城市名（字符串，如'杭州'）\n"
            "- days: 旅行天数（整数）\n"
            "- budget_per_day: 每日预算（数字，元）\n"
            "- total_budget: 总预算（数字，元）\n"
            "- pace: 节奏（'relaxed'/'moderate'/'intensive'）\n"
            "- transport_mode: 交通方式（'walking'/'public_transit'/'taxi'/'driving'）\n"
            "- holiday_hint: 节假日提示（如春节则填'spring_festival'）\n"
            "- travelers_count: 出行人数（整数）\n"
            "- must_visit: 必去景点列表（字符串数组）\n"
            "- free_only: 是否仅免费景点（布尔值）\n"
            "- themes: 偏好主题列表（如['历史','美食','自然','亲子','夜景']）\n"
            "- travelers_type: 出行人群（'solo'/'couple'/'family'/'friends'/'elderly'）\n"
            "- food_constraints: 饮食禁忌列表（如['素食','清真','无辣']）\n"
            "\n用户未提及的字段请省略不写。\n\n"
            f"用户消息：{text}"
        )
        resp = llm.invoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)

        # 尝试提取 JSON（可能被 ```json 包裹）
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return _json.loads(content)
    except Exception:
        return None


def intake_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Intake 节点：解析最后一条用户消息，填充 constraints/profile，
    检查缺参并设置 requirements_missing。
    优先用 LLM 提取，LLM 不可用时降级到正则。
    """
    messages = state.get("messages", [])
    if not messages:
        return {"requirements_missing": ["city", "days"], "status": "clarifying"}

    last = messages[-1]
    last_msg = last.get("content", "") if isinstance(last, dict) else str(last)

    # 解析约束
    constraints = state.get("trip_constraints", {})
    if isinstance(constraints, dict):
        c = dict(constraints)
    else:
        c = constraints.model_dump() if hasattr(constraints, "model_dump") else dict(constraints)

    profile = state.get("user_profile", {})
    if isinstance(profile, dict):
        p = dict(profile)
    else:
        p = profile.model_dump() if hasattr(profile, "model_dump") else dict(profile)

    # ── 尝试 LLM 提取 ──
    llm_result = _llm_extract(last_msg) if _use_llm_extract() else None

    if llm_result and isinstance(llm_result, dict):
        apply_llm_result(llm_result, c, p)
        # 以文本证据兜底，避免 LLM 将“北京3天”误改成其他城市/天数
        apply_text_evidence(last_msg, c, p)
    else:
        # ── 降级到正则提取 ──
        regex_extract(last_msg, c, p)

    # 检查缺参
    missing = check_missing(c, p)

    status = "clarifying" if missing else "planning"

    return {
        "trip_constraints": c,
        "user_profile": p,
        "requirements_missing": missing,
        "status": status,
    }
