"""Run fingerprint schema and builder."""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, Field

from app.config.settings import resolve_provider_snapshot


class RunMode(str, Enum):
    REALTIME = "REALTIME"
    DEGRADED = "DEGRADED"


class RunFingerprint(BaseModel):
    run_mode: RunMode = Field(default=RunMode.DEGRADED)
    poi_provider: str = Field(default="mock")
    route_provider: str = Field(default="fixture")
    llm_provider: str = Field(default="template")
    strict_external_data: bool = Field(default=False)
    env_source: str = Field(default=".env")
    trace_id: str = Field(default="")


def _effective_route_provider(
    itinerary: Mapping[str, Any] | None,
    default_route_provider: str,
) -> str:
    if not isinstance(itinerary, Mapping):
        return default_route_provider
    raw = str(itinerary.get("routing_source", "")).strip().lower()
    if raw:
        return raw
    return default_route_provider


def _compute_run_mode(*, poi_provider: str, route_provider: str, llm_provider: str) -> RunMode:
    degraded = (
        poi_provider != "amap"
        or route_provider not in {"real"}
        or llm_provider == "template"
        or "fallback" in route_provider
    )
    return RunMode.DEGRADED if degraded else RunMode.REALTIME


def build_run_fingerprint(
    *,
    trace_id: str,
    itinerary: Mapping[str, Any] | None = None,
    route_provider: str | None = None,
    env_source: str | None = None,
) -> RunFingerprint:
    snapshot = resolve_provider_snapshot(
        route_provider=route_provider,
        env_source=env_source,
    )
    effective_route_provider = _effective_route_provider(itinerary, snapshot.route_provider)
    run_mode = _compute_run_mode(
        poi_provider=snapshot.poi_provider,
        route_provider=effective_route_provider,
        llm_provider=snapshot.llm_provider,
    )
    return RunFingerprint(
        run_mode=run_mode,
        poi_provider=snapshot.poi_provider,
        route_provider=effective_route_provider,
        llm_provider=snapshot.llm_provider,
        strict_external_data=snapshot.strict_external_data,
        env_source=snapshot.env_source,
        trace_id=trace_id,
    )


__all__ = [
    "RunFingerprint",
    "RunMode",
    "build_run_fingerprint",
]

