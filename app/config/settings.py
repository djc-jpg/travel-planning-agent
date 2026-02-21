"""Runtime provider snapshot helpers."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

_TRUTHY = {"1", "true", "yes", "on"}


def _is_enabled(value: str | None) -> bool:
    return bool(value and value.strip().lower() in _TRUTHY)


def _is_configured(value: str | None) -> bool:
    return bool(value and value.strip())


def resolve_poi_provider() -> str:
    return "amap" if _is_configured(os.getenv("AMAP_API_KEY")) else "mock"


def resolve_llm_provider() -> str:
    if _is_configured(os.getenv("DASHSCOPE_API_KEY")):
        return "dashscope"
    if _is_configured(os.getenv("OPENAI_API_KEY")):
        return "openai"
    if _is_configured(os.getenv("LLM_API_KEY")):
        return "llm_compatible"
    return "template"


def resolve_route_provider_default() -> str:
    raw_mode = os.getenv("ROUTING_PROVIDER")
    mode = str(raw_mode or "").strip().lower()
    if mode in {"real", "fixture", "auto"}:
        return mode
    if _is_configured(os.getenv("AMAP_API_KEY")):
        # Prefer realtime routing when AMap credentials exist and no explicit override is set.
        return "real"
    return "fixture"


def strict_external_data_enabled() -> bool:
    return _is_enabled(os.getenv("STRICT_EXTERNAL_DATA"))


def resolve_env_source() -> str:
    explicit = str(os.getenv("ENV_SOURCE") or os.getenv("APP_ENV_SOURCE") or "").strip()
    if explicit:
        return explicit

    hint = str(os.getenv("ENV_FILE") or os.getenv("DOTENV_FILE") or "").strip()
    if hint:
        return Path(hint).name or hint

    redis_url = str(os.getenv("REDIS_URL") or "").strip().lower()
    if "redis://redis:6379" in redis_url:
        return ".env.prerelease"
    return ".env"


class ProviderSnapshot(BaseModel):
    poi_provider: str = Field(default="mock")
    route_provider: str = Field(default="fixture")
    llm_provider: str = Field(default="template")
    strict_external_data: bool = Field(default=False)
    env_source: str = Field(default=".env")


def resolve_provider_snapshot(
    *,
    route_provider: str | None = None,
    env_source: str | None = None,
) -> ProviderSnapshot:
    resolved_route = str(route_provider or "").strip().lower() or resolve_route_provider_default()
    resolved_env = str(env_source or "").strip() or resolve_env_source()
    return ProviderSnapshot(
        poi_provider=resolve_poi_provider(),
        route_provider=resolved_route,
        llm_provider=resolve_llm_provider(),
        strict_external_data=strict_external_data_enabled(),
        env_source=resolved_env,
    )


__all__ = [
    "ProviderSnapshot",
    "resolve_provider_snapshot",
]
