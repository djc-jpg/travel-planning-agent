"""需求定义：必填字段列表与默认值策略"""

from __future__ import annotations

# 必填字段（至少要有值才能进入规划）
REQUIRED_FIELDS = ["city", "days"]

# 推荐提供但可使用默认值
OPTIONAL_WITH_DEFAULTS = {
    "pace": "moderate",
    "transport_mode": "public_transit",
    "travelers_type": "couple",
}

# 字段中文名映射（用于追问）
FIELD_LABELS = {
    "city": "目的地城市",
    "days": "旅行天数",
    "budget_per_day": "每日预算",
    "total_budget": "总预算",
    "pace": "旅行节奏（轻松/适中/特种兵）",
    "themes": "偏好主题（如文艺、美食、亲子、历史）",
    "transport_mode": "交通方式",
    "travelers_type": "出行人群（独行/情侣/家庭/朋友/老年）",
    "food_constraints": "饮食禁忌",
}


def check_missing(constraints_dict: dict, profile_dict: dict) -> list[str]:
    """检查缺少的必填字段，返回缺失字段名列表。"""
    missing = []
    for field in REQUIRED_FIELDS:
        val = constraints_dict.get(field)
        if val is None or val == "" or val == 0:
            missing.append(field)
    return missing
