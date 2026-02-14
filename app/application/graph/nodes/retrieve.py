"""Retrieve 节点 — 通过 config 自动选择 mock/real POI 工具，无数据时 LLM 兜底生成
同时查询天气与日历信息供后续规划使用。
"""

from __future__ import annotations

import json as _json
from datetime import datetime
from typing import Any

from app.adapters.tool_factory import get_calendar_tool, get_poi_tool, get_weather_tool
from app.domain.models import POI, Severity, ValidationIssue
from app.infrastructure.logging import get_logger
from app.tools.interfaces import CalendarInput, POISearchInput, WeatherInput


def _llm_generate_pois(city: str, themes: list[str], count: int = 15) -> list[POI]:
    """
    当本地数据和真实 API 都无结果时，用 LLM 生成 POI 候选。
    """
    try:
        from app.infrastructure.llm_factory import get_llm

        llm = get_llm()
        if llm is None:
            return []

        themes_str = "、".join(themes) if themes else "综合"
        prompt = (
            f"你是一位{city}旅游专家。请推荐{city}的{count}个真实存在的热门景点/美食/体验，"
            f"用户偏好主题：{themes_str}。\n\n"
            f"请返回 JSON 数组，每个元素包含以下字段：\n"
            f"- id: 字符串，格式如 'llm_001'\n"
            f"- name: 景点名称\n"
            f"- city: '{city}'\n"
            f"- lat: 纬度（真实坐标，保留4位小数）\n"
            f"- lon: 经度（真实坐标，保留4位小数）\n"
            f"- themes: 主题标签数组（从 历史/美食/自然/文艺/网红/亲子/购物/夜景/地标/艺术/博物馆/园林/文化 中选）\n"
            f"- duration_hours: 建议游玩时长（小时，数字）\n"
            f"- cost: 门票/人均费用（元，数字，免费填0）\n"
            f"- indoor: 是否室内（布尔值）\n"
            f"- open_time: 开放时间（字符串，如'08:00-17:00'或'全天'）\n"
            f"- description: 一句话描述（20字以内）\n\n"
            f"请确保景点真实存在，坐标准确。只返回 JSON 数组，不要其他文字。"
        )
        resp = llm.invoke(prompt)
        content = resp.content if hasattr(resp, "content") else str(resp)
        content = content.strip()

        # 处理可能的 ```json 包裹
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        raw_list = _json.loads(content)
        pois = []
        for idx, raw in enumerate(raw_list):
            try:
                raw["id"] = raw.get("id", f"llm_{idx:03d}")
                raw["city"] = city
                pois.append(POI.model_validate(raw))
            except Exception:
                continue
        return pois
    except Exception:
        return []


def retrieve_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Retrieve 节点：根据 trip_constraints 和 user_profile 搜索候选 POI。
    数据源优先级：real API → mock 本地数据 → LLM 生成。
    """
    constraints = state.get("trip_constraints", {})
    profile = state.get("user_profile", {})

    city = constraints.get("city", "") if isinstance(constraints, dict) else getattr(constraints, "city", "")
    themes = profile.get("themes", []) if isinstance(profile, dict) else getattr(profile, "themes", [])

    if not city:
        return {
            "attraction_candidates": [],
            "validation_issues": [
                ValidationIssue(
                    code="NO_CANDIDATES",
                    severity=Severity.HIGH,
                    message="未指定城市，无法搜索景点",
                ).model_dump(mode="json")
            ],
        }

    # 1️⃣ 尝试 config 选择的工具 (real API 或 mock)
    params = POISearchInput(city=city, themes=themes, max_results=30)
    poi_tool = get_poi_tool()
    candidates = poi_tool.search_poi(params)

    if not candidates:
        # 降级：不带主题再搜一次
        params_fallback = POISearchInput(city=city, max_results=30)
        candidates = poi_tool.search_poi(params_fallback)

    # 2️⃣ 本地/API 无数据 → LLM 生成兜底
    if not candidates:
        candidates = _llm_generate_pois(city, themes)

    if not candidates:
        return {
            "attraction_candidates": [],
            "validation_issues": [
                ValidationIssue(
                    code="NO_CANDIDATES",
                    severity=Severity.HIGH,
                    message=f"在 {city} 未找到匹配的景点候选",
                    suggestions=["检查城市名称是否正确", "扩大主题范围"],
                ).model_dump(mode="json")
            ],
        }

    # 3️⃣ 查询天气 & 日历信息
    weather_data = None
    calendar_data = None
    days = constraints.get("days", 3) if isinstance(constraints, dict) else getattr(constraints, "days", 3)
    date_start = constraints.get("date_start") if isinstance(constraints, dict) else getattr(constraints, "date_start", None)
    date_str = str(date_start) if date_start else datetime.now().strftime("%Y-%m-%d")

    try:
        weather_tool = get_weather_tool()
        weather_result = weather_tool.get_weather(WeatherInput(
            city=city, date_start=date_str, days=days,
        ))
        weather_data = weather_result.model_dump(mode="json")
    except Exception as e:
        _retrieve_logger = get_logger()
        _retrieve_logger.warning("retrieve", f"天气查询失败，跳过: {e}")

    try:
        calendar_tool = get_calendar_tool()
        calendar_result = calendar_tool.get_calendar(CalendarInput(
            date_start=date_str, days=days,
        ))
        calendar_data = calendar_result.model_dump(mode="json")
    except Exception as e:
        _retrieve_logger = get_logger()
        _retrieve_logger.warning("retrieve", f"日历查询失败，跳过: {e}")

    return {
        "attraction_candidates": [c.model_dump(mode="json") for c in candidates],
        "validation_issues": [],
        "weather_data": weather_data,
        "calendar_data": calendar_data,
    }
