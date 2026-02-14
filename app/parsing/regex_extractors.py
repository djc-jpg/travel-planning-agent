"""公共解析工具函数 — 从文本中提取旅行相关字段

供 intake / merge_user_update 共用，避免跨模块导入私有函数。
"""

from __future__ import annotations

import re

from app.domain.models import Pace, TransportMode, TravelersType

# ── 城市名识别 ────────────────────────────

KNOWN_CITIES = [
    "北京", "上海", "广州", "深圳", "成都", "杭州", "西安", "南京",
    "重庆", "武汉", "长沙", "厦门", "青岛", "大理", "丽江", "三亚",
]

PACE_MAP: dict[str, Pace] = {
    "轻松": Pace.RELAXED,
    "休闲": Pace.RELAXED,
    "适中": Pace.MODERATE,
    "正常": Pace.MODERATE,
    "特种兵": Pace.INTENSIVE,
    "紧凑": Pace.INTENSIVE,
    "暴走": Pace.INTENSIVE,
}

TRANSPORT_MAP: dict[str, TransportMode] = {
    "步行": TransportMode.WALKING,
    "走路": TransportMode.WALKING,
    "公交": TransportMode.PUBLIC_TRANSIT,
    "地铁": TransportMode.PUBLIC_TRANSIT,
    "公共交通": TransportMode.PUBLIC_TRANSIT,
    "打车": TransportMode.TAXI,
    "出租车": TransportMode.TAXI,
    "网约车": TransportMode.TAXI,
    "开车": TransportMode.DRIVING,
    "自驾": TransportMode.DRIVING,
}

TRAVELERS_MAP: dict[str, TravelersType] = {
    "一个人": TravelersType.SOLO,
    "独自": TravelersType.SOLO,
    "情侣": TravelersType.COUPLE,
    "两个人": TravelersType.COUPLE,
    "家庭": TravelersType.FAMILY,
    "亲子": TravelersType.FAMILY,
    "带孩子": TravelersType.FAMILY,
    "朋友": TravelersType.FRIENDS,
    "闺蜜": TravelersType.FRIENDS,
    "老人": TravelersType.ELDERLY,
    "老年": TravelersType.ELDERLY,
}

THEME_KEYWORDS = [
    "文艺", "美食", "历史", "自然", "网红", "亲子", "艺术",
    "购物", "夜景", "博物馆", "园林", "乐园", "科技", "体育", "地标",
]

FOOD_KEYWORDS = ["素食", "清真", "无辣", "不吃辣", "海鲜过敏", "无麸质"]


def extract_city(text: str) -> str | None:
    """从文本中提取城市名。"""
    for city in KNOWN_CITIES:
        if city in text:
            return city
    m = re.search(r"去(\S{2,4}?)(?:玩|旅|游|逛|走走|看看|行|$)", text)
    return m.group(1) if m else None


def extract_days(text: str) -> int | None:
    """从文本中提取天数。"""
    m = re.search(r"(\d+)\s*[天日]", text)
    return int(m.group(1)) if m else None


def extract_budget(text: str) -> float | None:
    """从文本中提取预算金额。"""
    m = re.search(r"预算\s*(\d+)", text)
    if m:
        return float(m.group(1))
    m = re.search(r"每天\s*(\d+)\s*元", text)
    return float(m.group(1)) if m else None


def regex_extract(text: str, constraints: dict, profile: dict) -> None:
    """用正则从 text 中提取信息，就地更新 constraints 和 profile。"""
    city = extract_city(text)
    if city:
        constraints["city"] = city

    days = extract_days(text)
    if days:
        constraints["days"] = days

    budget = extract_budget(text)
    if budget:
        if "每天" in text:
            constraints["budget_per_day"] = budget
        else:
            constraints["total_budget"] = budget

    for kw, pace in PACE_MAP.items():
        if kw in text:
            constraints["pace"] = pace.value
            break

    for kw, mode in TRANSPORT_MAP.items():
        if kw in text:
            constraints["transport_mode"] = mode.value
            break

    for kw, tt in TRAVELERS_MAP.items():
        if kw in text:
            profile["travelers_type"] = tt.value
            break

    themes = profile.get("themes", [])
    for th in THEME_KEYWORDS:
        if th in text and th not in themes:
            themes.append(th)
    profile["themes"] = themes

    food = profile.get("food_constraints", [])
    for kw in FOOD_KEYWORDS:
        if kw in text and kw not in food:
            food.append(kw)
    profile["food_constraints"] = food


def apply_llm_result(result: dict, constraints: dict, profile: dict) -> None:
    """将 LLM 提取结果合并到 constraints / profile，就地更新。"""
    if result.get("city"):
        constraints["city"] = result["city"]
    if result.get("days"):
        constraints["days"] = int(result["days"])
    if result.get("budget_per_day"):
        constraints["budget_per_day"] = float(result["budget_per_day"])
    if result.get("total_budget"):
        constraints["total_budget"] = float(result["total_budget"])
    if result.get("pace"):
        constraints["pace"] = result["pace"]
    if result.get("transport_mode"):
        constraints["transport_mode"] = result["transport_mode"]
    if result.get("themes"):
        existing = profile.get("themes", [])
        for t in result["themes"]:
            if t not in existing:
                existing.append(t)
        profile["themes"] = existing
    if result.get("travelers_type"):
        profile["travelers_type"] = result["travelers_type"]
    if result.get("food_constraints"):
        existing_food = profile.get("food_constraints", [])
        for f in result["food_constraints"]:
            if f not in existing_food:
                existing_food.append(f)
        profile["food_constraints"] = existing_food
