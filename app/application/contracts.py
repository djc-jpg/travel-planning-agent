"""Application request/response contracts."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from app.config.runtime_fingerprint import RunFingerprint


class TripStatus(str, Enum):
    DONE = "done"
    CLARIFYING = "clarifying"
    ERROR = "error"


class EvidenceSource(str, Enum):
    USER_TEXT = "user_text"
    USER_FORM = "user_form"
    LLM_GUESS = "llm_guess"
    DEFAULT = "default"


class FieldEvidence(BaseModel):
    field: str
    source: EvidenceSource
    value: Any | None = None


class TripRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, min_length=1, max_length=64)
    constraints: dict[str, Any] = Field(default_factory=dict)
    user_profile: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TripResult(BaseModel):
    status: TripStatus
    message: str = ""
    itinerary: dict[str, Any] | None = None
    session_id: str = ""
    request_id: str = ""
    trace_id: str = ""
    degrade_level: str = "L0"
    confidence_score: float | None = None
    issues: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    field_evidence: dict[str, FieldEvidence] = Field(default_factory=dict)
    run_fingerprint: RunFingerprint | None = None
