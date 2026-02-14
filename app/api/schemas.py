"""API 请求/响应模型"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class PlanRequest(BaseModel):
    """一次性规划请求"""
    message: str = Field(description="用户输入的旅行需求")


class ChatRequest(BaseModel):
    """多轮对话请求"""
    session_id: str = Field(default="default")
    message: str = Field(description="用户消息")


class PlanResponse(BaseModel):
    """规划响应"""
    status: str = Field(description="done / clarifying / error")
    message: str = Field(default="", description="助手回复文本")
    itinerary: Optional[dict[str, Any]] = Field(default=None, description="最终行程 JSON")
    session_id: str = Field(default="")


class HealthResponse(BaseModel):
    status: str = "ok"
