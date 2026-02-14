"""Finalize 节点 — 输出最终行程"""

from __future__ import annotations

from typing import Any

from app.domain.models import Itinerary


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

        # 补充总结
        if not itinerary.summary:
            day_strs = []
            for d in itinerary.days:
                names = [s.poi.name for s in d.schedule if not s.is_backup]
                day_strs.append(f"第{d.day_number}天: {'→'.join(names)}")
            itinerary.summary = f"{itinerary.city}{len(itinerary.days)}日行程\n" + "\n".join(day_strs)

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
