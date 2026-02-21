"""Persistence-layer record schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SessionRecord(BaseModel):
    session_id: str
    updated_at: str
    status: str = ""
    trace_id: str = ""


class RequestRecord(BaseModel):
    request_id: str
    session_id: str
    trace_id: str
    message: str
    constraints: dict[str, Any] = Field(default_factory=dict)
    user_profile: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class PlanRecord(BaseModel):
    request_id: str
    session_id: str
    trace_id: str
    status: str
    degrade_level: str
    confidence_score: float | None = None
    run_fingerprint: dict[str, Any] | None = None
    itinerary: dict[str, Any] | None = None
    issues: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    field_evidence: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ArtifactRecord(BaseModel):
    request_id: str
    artifact_type: str
    payload: dict[str, Any]
    created_at: str


class SessionSummaryItem(BaseModel):
    session_id: str
    updated_at: str
    last_status: str
    last_trace_id: str


class SessionHistoryItem(BaseModel):
    request_id: str
    session_id: str
    trace_id: str
    message: str
    status: str
    degrade_level: str
    confidence_score: float | None = None
    run_fingerprint: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ArtifactPayload(BaseModel):
    artifact_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class PlanExportRecord(BaseModel):
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
    itinerary: dict[str, Any] | None = None
    issues: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    field_evidence: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    artifacts: list[ArtifactPayload] = Field(default_factory=list)


__all__ = [
    "ArtifactPayload",
    "ArtifactRecord",
    "PlanExportRecord",
    "PlanRecord",
    "RequestRecord",
    "SessionHistoryItem",
    "SessionSummaryItem",
    "SessionRecord",
]
