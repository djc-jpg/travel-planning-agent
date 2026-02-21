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
    constraints: dict[str, Any] = Field(default_factory=dict, description="结构化行程约束")
    user_profile: dict[str, Any] = Field(default_factory=dict, description="用户画像信息")
    metadata: dict[str, Any] = Field(default_factory=dict, description="请求元数据")


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
    constraints: dict[str, Any] = Field(default_factory=dict, description="结构化行程约束")
    user_profile: dict[str, Any] = Field(default_factory=dict, description="用户画像信息")
    metadata: dict[str, Any] = Field(default_factory=dict, description="请求元数据")


class RunFingerprintResponse(BaseModel):
    run_mode: str = Field(default="DEGRADED")
    poi_provider: str = Field(default="mock")
    route_provider: str = Field(default="fixture")
    llm_provider: str = Field(default="template")
    strict_external_data: bool = Field(default=False)
    env_source: str = Field(default=".env")
    trace_id: str = Field(default="")


class PlanResponse(BaseModel):
    status: str = Field(description="done / clarifying / error")
    message: str = Field(default="", description="助手回复文本")
    itinerary: Optional[dict[str, Any]] = Field(default=None, description="最终行程 JSON")
    session_id: str = Field(default="")
    request_id: str = Field(default="")
    trace_id: str = Field(default="")
    degrade_level: str = Field(default="L0")
    confidence_score: float | None = Field(default=None)
    issues: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    field_evidence: dict[str, Any] = Field(default_factory=dict)
    run_fingerprint: RunFingerprintResponse | None = None


class HealthResponse(BaseModel):
    status: str = "ok"


class SessionHistoryItemResponse(BaseModel):
    request_id: str
    trace_id: str
    message: str
    status: str
    degrade_level: str
    confidence_score: float | None = None
    run_fingerprint: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class SessionHistoryResponse(BaseModel):
    session_id: str
    items: list[SessionHistoryItemResponse] = Field(default_factory=list)


class SessionSummaryItemResponse(BaseModel):
    session_id: str
    updated_at: str
    last_status: str
    last_trace_id: str


class SessionListResponse(BaseModel):
    items: list[SessionSummaryItemResponse] = Field(default_factory=list)


class ArtifactPayloadResponse(BaseModel):
    artifact_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class PlanExportResponse(BaseModel):
    request_id: str
    session_id: str
    trace_id: str
    message: str
    constraints: dict[str, Any] = Field(default_factory=dict)
    user_profile: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: str
    degrade_level: str
    confidence_score: float | None = None
    run_fingerprint: dict[str, Any] = Field(default_factory=dict)
    itinerary: Optional[dict[str, Any]] = None
    issues: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    field_evidence: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    artifacts: list[ArtifactPayloadResponse] = Field(default_factory=list)
