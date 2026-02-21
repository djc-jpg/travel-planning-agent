"""Finalize 节点 — 输出最终行程"""

from __future__ import annotations

import re
from typing import Any

from app.domain.models import Itinerary

_MACHINE_SUMMARY_HINTS = re.compile(r"(executable itinerary|day\s*\d+\s*:)", re.IGNORECASE)
_DAY_SEGMENT_RE = re.compile(r"day\s*(\d+)\s*:\s*([^;|]+)", re.IGNORECASE)
_FORMULA_SUMMARY_HINTS = re.compile(r"\d+天可执行行程[：:]", re.IGNORECASE)


def _build_human_summary(itinerary: Itinerary) -> str:
    rows: list[str] = []
    for day in itinerary.days:
        names = [item.poi.name for item in day.schedule if not item.is_backup]
        if not names:
            continue
        rows.append(f"第{day.day_number}天：{'、'.join(names)}")
    prefix = f"{itinerary.city}{len(itinerary.days)}天行程亮点"
    return f"{prefix}：{'；'.join(rows)}" if rows else f"{itinerary.city}{len(itinerary.days)}天行程已生成"


def _normalize_summary(itinerary: Itinerary) -> str:
    city_days_prefix = f"{itinerary.city}{len(itinerary.days)}天"
    raw = str(itinerary.summary or "").strip()
    if not raw:
        return _build_human_summary(itinerary)
    if _FORMULA_SUMMARY_HINTS.search(raw):
        separator = "：" if "：" in raw else (":" if ":" in raw else "")
        suffix = raw.split(separator, 1)[1].strip() if separator else ""
        return (
            f"{city_days_prefix}行程亮点：{suffix}"
            if suffix
            else f"{city_days_prefix}行程已生成"
        )
    if not _MACHINE_SUMMARY_HINTS.search(raw):
        return raw

    rows: list[str] = []
    for match in _DAY_SEGMENT_RE.finditer(raw):
        day = int(match.group(1))
        names = "、".join(name.strip() for name in match.group(2).split("->") if name.strip())
        if names:
            rows.append(f"第{day}天：{names}")
    if rows:
        return f"{city_days_prefix}行程亮点：{'；'.join(rows)}"
    return _build_human_summary(itinerary)


def finalize_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Finalize 节点：
    1. 将 itinerary_draft 通过 Pydantic 校验
    2. 写入 final_itinerary
    3. 生成面向用户的总结文本
    """
    draft_raw = state.get("itinerary_draft")
    if draft_raw is None:
        return {
            "status": "error",
            "messages": state.get("messages", []) + [
                {"role": "assistant", "content": "抱歉，行程生成失败，请重试。"}
            ],
        }

    try:
        itinerary = Itinerary.model_validate(draft_raw) if isinstance(draft_raw, dict) else draft_raw

        # 输出前统一规范 summary，避免机器模板直出给用户。
        itinerary.summary = _normalize_summary(itinerary)

        messages = list(state.get("messages", []))
        messages.append({"role": "assistant", "content": itinerary.summary})

        return {
            "final_itinerary": itinerary.model_dump(mode="json"),
            "status": "done",
            "messages": messages,
        }
    except Exception as e:
        return {
            "status": "error",
            "messages": state.get("messages", []) + [
                {"role": "assistant", "content": f"行程校验失败: {e}"}
            ],
        }
