"""API request/response models."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

_SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]+$"


class PlanRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=2000,
        description="用户输入的旅行需求",
    )


class ChatRequest(BaseModel):
    session_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=_SESSION_ID_PATTERN,
        description="会话 ID，仅允许字母数字、下划线和中划线",
    )
    message: str = Field(
        min_length=1,
        max_length=2000,
        description="用户消息",
    )


class PlanResponse(BaseModel):
    status: str = Field(description="done / clarifying / error")
    message: str = Field(default="", description="助手回复文本")
    itinerary: Optional[dict[str, Any]] = Field(default=None, description="最终行程 JSON")
    session_id: str = Field(default="")


class HealthResponse(BaseModel):
    status: str = "ok"

