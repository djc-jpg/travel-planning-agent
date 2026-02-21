"""FastAPI app with security hardening."""

from __future__ import annotations

import logging
import os
import secrets
import time
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.schemas import (
    ChatRequest,
    HealthResponse,
    PlanExportResponse,
    PlanRequest,
    PlanResponse,
    SessionHistoryResponse,
    SessionListResponse,
)
from app.application.context import make_app_context
from app.application.contracts import TripResult
from app.application.plan_trip import GraphTimeoutError
from app.infrastructure.rate_limiter import get_rate_limiter
from app.services.history_service import get_plan_export, list_session_history, list_sessions
from app.services.export_formatter import render_plan_markdown
from app.services.plan_service import execute_plan

_api_logger = logging.getLogger("trip-agent.api")

load_dotenv()

app = FastAPI(
    title="trip-agent",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "false").lower() == "true" else None,
    redoc_url=None,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Lightweight access logging with latency and request ID."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        request_id = request.headers.get("x-request-id", str(uuid.uuid4())[:12])
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            _api_logger.info(
                "request_id=%s method=%s path=%s status=%s duration_ms=%s",
                request_id,
                request.method,
                request.url.path,
                status_code,
                duration_ms,
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self._limiter = get_rate_limiter(max_requests=max_requests, window_seconds=window_seconds)

    async def dispatch(self, request: Request, call_next):
        if request.method != "POST":
            return await call_next(request)

        client_ip = _extract_client_ip(request)
        if not self._limiter.allow(client_ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
            )
        return await call_next(request)


def _extract_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def _parse_cors_origins(raw: str | None) -> list[str]:
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or ["http://localhost:3000", "http://127.0.0.1:3000"]


def _is_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _check_diagnostics_access(request: Request) -> None:
    if not _is_enabled("ENABLE_DIAGNOSTICS", default=False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    expected = os.getenv("DIAGNOSTICS_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Diagnostics token is not configured",
        )

    provided = _extract_bearer_token(request.headers.get("Authorization"))
    if not provided:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bearer token")


def _check_api_access(request: Request) -> None:
    if _is_enabled("ALLOW_UNAUTHENTICATED_API", default=False):
        return

    expected = os.getenv("API_BEARER_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API auth is not configured; set API_BEARER_TOKEN or ALLOW_UNAUTHENTICATED_API=true",
        )

    provided = _extract_bearer_token(request.headers.get("Authorization"))
    if not provided:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bearer token")


app.add_middleware(RequestLogMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    max_requests=int(os.getenv("RATE_LIMIT_MAX", "60")),
    window_seconds=int(os.getenv("RATE_LIMIT_WINDOW", "60")),
)

_cors_origins = _parse_cors_origins(os.getenv("CORS_ORIGINS"))
_cors_allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true"
if "*" in _cors_origins and _cors_allow_credentials:
    _api_logger.warning(
        "CORS_ORIGINS contains '*' with credentials enabled; forcing allow_credentials=false"
    )
    _cors_allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_app_ctx = make_app_context()


def _result_to_response(result: TripResult) -> PlanResponse:
    return PlanResponse(
        status=result.status.value,
        message=result.message,
        itinerary=result.itinerary,
        session_id=result.session_id,
        request_id=result.request_id,
        trace_id=result.trace_id,
        degrade_level=result.degrade_level,
        confidence_score=result.confidence_score,
        issues=list(result.issues),
        next_questions=list(result.next_questions),
        field_evidence={
            name: item.model_dump(mode="json")
            for name, item in result.field_evidence.items()
        },
        run_fingerprint=(
            result.run_fingerprint.model_dump(mode="json")
            if result.run_fingerprint is not None
            else None
        ),
    )


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@app.get("/metrics")
def metrics():
    from app.observability.plan_metrics import get_plan_metrics

    return get_plan_metrics().snapshot()


@app.get("/diagnostics")
def diagnostics(request: Request):
    _check_diagnostics_access(request)

    from app.adapters.tool_factory import describe_active_tools
    from app.infrastructure.cache import poi_cache, route_cache, weather_cache
    from app.observability.plan_metrics import get_plan_metrics
    from app.security.amap_signer import is_signing_enabled

    return {
        "tools": describe_active_tools(),
        "signing_enabled": is_signing_enabled(),
        "cache": {
            "poi": poi_cache.stats,
            "route": route_cache.stats,
            "weather": weather_cache.stats,
        },
        "sessions": {
            "backend": getattr(_app_ctx.session_store, "backend", "unknown"),
            "active": _app_ctx.session_store.active_count,
        },
        "runtime_flags": {
            "engine_version": _app_ctx.engine_version,
            "strict_required_fields": _app_ctx.strict_required_fields,
        },
        "plan_metrics": get_plan_metrics().snapshot(),
    }


@app.get("/sessions", response_model=SessionListResponse)
def sessions(request: Request, limit: int = 20):
    _check_api_access(request)

    rows = list_sessions(ctx=_app_ctx, limit=limit)
    return SessionListResponse(items=[row.model_dump(mode="json") for row in rows])


@app.get("/sessions/{session_id}/history", response_model=SessionHistoryResponse)
def session_history(session_id: str, request: Request, limit: int = 20):
    _check_api_access(request)

    rows = list_session_history(ctx=_app_ctx, session_id=session_id, limit=limit)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session history not found")
    return SessionHistoryResponse(
        session_id=session_id,
        items=[row.model_dump(mode="json") for row in rows],
    )


@app.get("/plans/{request_id}/export", response_model=PlanExportResponse)
def export_plan(request_id: str, request: Request, format: str = "json"):
    _check_api_access(request)

    record = get_plan_export(ctx=_app_ctx, request_id=request_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan export not found")

    normalized_format = format.strip().lower()
    if normalized_format == "json":
        return PlanExportResponse(**record.model_dump(mode="json"))
    if normalized_format == "markdown":
        markdown = render_plan_markdown(record)
        return PlainTextResponse(markdown, media_type="text/markdown; charset=utf-8")

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported export format; use json or markdown",
    )


@app.post("/plan", response_model=PlanResponse)
def plan(req: PlanRequest, request: Request, debug: bool = False):
    _check_api_access(request)

    try:
        result = execute_plan(
            ctx=_app_ctx,
            message=req.message,
            constraints=req.constraints,
            user_profile=req.user_profile,
            metadata=req.metadata,
            debug=debug,
        )
    except GraphTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"规划超时（{exc.timeout}秒），请简化需求后重试",
        ) from None
    except Exception as exc:
        _safe_log_exception("plan endpoint error", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="规划过程出错，请稍后重试",
        ) from None

    if result.status.value == "error":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.message or "无法生成可执行行程，请调整需求后重试",
        )
    return _result_to_response(result)


@app.post("/chat", response_model=PlanResponse)
def chat(req: ChatRequest, request: Request, debug: bool = False):
    _check_api_access(request)

    try:
        result = execute_plan(
            ctx=_app_ctx,
            message=req.message,
            session_id=req.session_id,
            constraints=req.constraints,
            user_profile=req.user_profile,
            metadata=req.metadata,
            debug=debug,
        )
    except GraphTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"对话处理超时（{exc.timeout}秒），请稍后重试",
        ) from None
    except Exception as exc:
        _safe_log_exception("chat endpoint error", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="对话处理出错，请稍后重试",
        ) from None

    if result.status.value == "error":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.message or "无法继续该会话，请调整需求后重试",
        )
    return _result_to_response(result)


def _safe_log_exception(context: str, exc: Exception) -> None:
    try:
        from app.security.key_manager import get_key_manager

        km = get_key_manager()
        safe_msg = km.scrub_text(str(exc))
        _api_logger.error("%s: %s", context, safe_msg)
    except Exception:
        _api_logger.error("%s: [exception details redacted]", context)
