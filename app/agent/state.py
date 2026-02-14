"""LangGraph Agent State — 可序列化"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.domain.models import (
    Itinerary,
    POI,
    TripConstraints,
    UserProfile,
    ValidationIssue,
)


class AgentState(BaseModel):
    """Agent 全局状态，使用 Pydantic 保证可序列化。"""

    # 对话消息（简化为 list[dict]）
    messages: list[dict[str, Any]] = Field(default_factory=list)

    # 用户信息
    user_profile: UserProfile = Field(default_factory=UserProfile)
    trip_constraints: TripConstraints = Field(default_factory=TripConstraints)

    # 需求解析
    requirements_missing: list[str] = Field(default_factory=list)

    # 候选 POI
    attraction_candidates: list[POI] = Field(default_factory=list)

    # 行程草案
    itinerary_draft: Optional[Itinerary] = None

    # 验证
    validation_issues: list[ValidationIssue] = Field(default_factory=list)

    # 最终行程
    final_itinerary: Optional[Itinerary] = None

    # 修复控制
    repair_attempts: int = 0
    max_repair_attempts: int = 3

    # 状态标记
    status: str = "init"  # init / clarifying / planning / done / error

    # 天气 & 日历上下文
    weather_data: Optional[dict[str, Any]] = None
    calendar_data: Optional[dict[str, Any]] = None

    # 可观测
    metrics: dict[str, Any] = Field(default_factory=dict)

    # ── 序列化 ────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict（可 JSON 化）。"""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentState":
        """从 dict 反序列化。"""
        return cls.model_validate(data)
