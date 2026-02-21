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
    patterns = [
        r"(?:总预算|预算(?:总共|共计|约|大概)?)[^\d]{0,6}(\d+)\s*元?",
        r"预算[^\d]{0,6}(\d+)\s*元?",
        r"每天[^\d]{0,4}(\d+)\s*元?",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return float(m.group(1))
    m = re.search(r"每天\s*(\d+)\s*元", text)
    return float(m.group(1)) if m else None


def extract_travelers_count(text: str) -> int | None:
    """Extract traveler count from common Chinese expressions."""
    patterns = [
        r"(\d+)\s*位",
        r"(\d+)\s*人",
        r"(\d+)\s*大人",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            value = int(m.group(1))
            if 1 <= value <= 20:
                return value
    return None


def extract_holiday_hint(text: str) -> str | None:
    if "春节" in text:
        return "spring_festival"
    if "国庆" in text:
        return "national_day"
    return None


def extract_free_only(text: str) -> bool:
    return any(
        kw in text
        for kw in (
            "只去免费",
            "免费景点",
            "不要收费",
            "不买门票",
            "免门票",
        )
    )


def extract_must_visit(text: str) -> list[str]:
    match = re.search(r"(?:必须去|必去)([^。；\n]+)", text)
    if not match:
        return []

    segment = match.group(1)
    # Remove trailing intent phrases that are not POI names.
    segment = re.split(r"(请|并|然后|希望|给我|安排)", segment)[0]
    raw_parts = re.split(r"[、,，和及]\s*", segment)
    cleaned: list[str] = []
    for part in raw_parts:
        token = part.strip("：: 。；;，,")
        if not token:
            continue
        if len(token) > 16:
            continue
        cleaned.append(token)
    return cleaned[:6]


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

    holiday_hint = extract_holiday_hint(text)
    if holiday_hint:
        constraints["holiday_hint"] = holiday_hint

    travelers_count = extract_travelers_count(text)
    if travelers_count:
        constraints["travelers_count"] = travelers_count

    if extract_free_only(text):
        constraints["free_only"] = True

    must_visit = extract_must_visit(text)
    if must_visit:
        constraints["must_visit"] = must_visit

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


def apply_text_evidence(text: str, constraints: dict, profile: dict) -> None:
    """Apply deterministic values explicitly mentioned in user text.

    This is intended as a safety guard after LLM extraction so that explicit
    user-provided facts (for example city/days) are not overwritten by model drift.
    """
    c_from_text: dict = {}
    p_from_text: dict = {}
    regex_extract(text, c_from_text, p_from_text)

    for key in (
        "city",
        "days",
        "budget_per_day",
        "total_budget",
        "pace",
        "transport_mode",
        "holiday_hint",
        "travelers_count",
        "free_only",
        "must_visit",
    ):
        if key in c_from_text:
            constraints[key] = c_from_text[key]

    if p_from_text.get("travelers_type"):
        profile["travelers_type"] = p_from_text["travelers_type"]

    themes = profile.get("themes", [])
    for theme in p_from_text.get("themes", []):
        if theme not in themes:
            themes.append(theme)
    profile["themes"] = themes

    food_constraints = profile.get("food_constraints", [])
    for item in p_from_text.get("food_constraints", []):
        if item not in food_constraints:
            food_constraints.append(item)
    profile["food_constraints"] = food_constraints


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
    if result.get("holiday_hint"):
        constraints["holiday_hint"] = result["holiday_hint"]
    if result.get("travelers_count"):
        constraints["travelers_count"] = int(result["travelers_count"])
    if result.get("free_only") is not None:
        constraints["free_only"] = bool(result["free_only"])
    if result.get("must_visit"):
        constraints["must_visit"] = [str(item) for item in result["must_visit"] if str(item).strip()]
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
