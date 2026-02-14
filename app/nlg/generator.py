"""Planner NLG — 为行程添加文案说明（LLM 或模板回退）"""

from __future__ import annotations

from app.infrastructure.llm_factory import get_llm
from app.domain.models import Itinerary, ScheduleItem
from app.infrastructure.logging import get_logger

# ── 模板文案 ──────────────────────────────────────────

_TEMPLATES = {
    "morning": "上午前往{name}，预计游玩{dur}小时。{desc}",
    "lunch": "午间可在{name}附近用餐或体验当地美食。{desc}",
    "afternoon": "下午游览{name}，感受{themes}的魅力。{desc}",
    "dinner": "傍晚到{name}享用晚餐或休闲漫步。{desc}",
    "evening": "晚间前往{name}，欣赏夜景或夜生活。{desc}",
}


def _template_note(item: ScheduleItem) -> str:
    tpl = _TEMPLATES.get(item.time_slot.value, "前往{name}。{desc}")
    themes_str = "、".join(item.poi.themes) if item.poi.themes else "旅行"
    return tpl.format(
        name=item.poi.name,
        dur=item.poi.duration_hours,
        desc=item.poi.description or "",
        themes=themes_str,
    )


def enrich_itinerary(itinerary: Itinerary) -> Itinerary:
    """为每个 ScheduleItem 补充 notes。"""
    llm = get_llm()
    _nlg_logger = get_logger()

    for day in itinerary.days:
        for item in day.schedule:
            if item.notes:
                continue  # 已有 notes 则跳过
            if llm is not None:
                # LLM 模式
                try:
                    prompt = (
                        f"你是一位资深旅行达人，请为以下景点写一段详细的旅行攻略（100-150字），"
                        f"包含：推荐理由、最佳游玩方式、必看亮点、实用小贴士。\n\n"
                        f"景点名: {item.poi.name}\n"
                        f"城市: {item.poi.city}\n"
                        f"描述: {item.poi.description}\n"
                        f"主题标签: {', '.join(item.poi.themes)}\n"
                        f"建议游玩时长: {item.poi.duration_hours}小时\n"
                        f"时间段: {item.time_slot.value}\n"
                        f"门票参考: {'免费' if item.poi.cost == 0 else f'{item.poi.cost}元'}\n"
                        f"\n请直接输出攻略文字，不要加标题或序号。"
                    )
                    resp = llm.invoke(prompt)  # type: ignore
                    item.notes = resp.content if hasattr(resp, "content") else str(resp)
                except Exception as e:
                    _nlg_logger.warning("planner_nlg", f"LLM 生成景点文案失败({item.poi.name}): {e}")
                    item.notes = _template_note(item)
            else:
                item.notes = _template_note(item)

        # 用 LLM 生成每天摘要
        if not day.day_summary:
            poi_names = [s.poi.name for s in day.schedule if not s.is_backup]
            if llm is not None:
                try:
                    day_prompt = (
                        f"请用一段流畅的话（50-80字）概括这一天的行程安排，"
                        f"体现游玩节奏和亮点：\n"
                        f"第{day.day_number}天行程：{'→'.join(poi_names)}\n"
                        f"请直接输出，不要加'第X天'开头。"
                    )
                    resp = llm.invoke(day_prompt)  # type: ignore
                    text = resp.content if hasattr(resp, "content") else str(resp)
                    day.day_summary = f"第{day.day_number}天：{text.strip()}"
                except Exception as e:
                    _nlg_logger.warning("planner_nlg", f"LLM 生成日总结失败(第{day.day_number}天): {e}")
                    day.day_summary = f"第{day.day_number}天：{'→'.join(poi_names)}"
            else:
                day.day_summary = f"第{day.day_number}天：{'→'.join(poi_names)}"

    # 总结
    if not itinerary.summary:
        if llm is not None:
            try:
                all_pois = [s.poi.name for d in itinerary.days for s in d.schedule if not s.is_backup]
                summary_prompt = (
                    f"请为{itinerary.city}{len(itinerary.days)}日旅行写一段总结推荐语（80-120字），"
                    f"涵盖行程要覆盖的景点和体验亮点。\n"
                    f"包含的景点：{'、'.join(all_pois)}\n"
                    f"请直接输出，语气热情自然。"
                )
                resp = llm.invoke(summary_prompt)  # type: ignore
                itinerary.summary = resp.content if hasattr(resp, "content") else str(resp)
            except Exception as e:
                _nlg_logger.warning("planner_nlg", f"LLM 生成行程总结失败: {e}")
                day_summaries = [d.day_summary for d in itinerary.days]
                itinerary.summary = f"{itinerary.city}{len(itinerary.days)}日行程：" + "；".join(day_summaries)
        else:
            day_summaries = [d.day_summary for d in itinerary.days]
            itinerary.summary = f"{itinerary.city}{len(itinerary.days)}日行程：" + "；".join(day_summaries)

    return itinerary
