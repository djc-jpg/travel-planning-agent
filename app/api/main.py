"""FastAPI app with security hardening."""

from __future__ import annotations

import concurrent.futures
import logging
import os
import secrets
import time
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.agent.nodes.merge_user_update import merge_user_update_node
from app.api.schemas import ChatRequest, HealthResponse, PlanRequest, PlanResponse
from app.application.graph.workflow import compile_graph
from app.application.state_factory import make_initial_state
from app.infrastructure.rate_limiter import get_rate_limiter
from app.infrastructure.session_store import get_session_store

_api_logger = logging.getLogger("trip-agent.api")

load_dotenv()

_GRAPH_TIMEOUT = int(os.getenv("GRAPH_TIMEOUT_SECONDS", "120"))

app = FastAPI(
    title="trip-agent",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "false").lower() == "true" else None,
    redoc_url=None,
)


class GraphTimeoutError(RuntimeError):
    """Raised when graph invocation exceeds timeout."""

    def __init__(self, timeout: int):
        self.timeout = timeout
        super().__init__(f"graph invoke timed out after {timeout}s")


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
    expected = os.getenv("API_BEARER_TOKEN", "").strip()
    if not expected:
        return

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
    _api_logger.warning("CORS_ORIGINS contains '*' with credentials enabled; forcing allow_credentials=false")
    _cors_allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

store = get_session_store()
_compiled_graph = None


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = compile_graph()
    return _compiled_graph


def _invoke_with_timeout(graph, state: dict, timeout: int = _GRAPH_TIMEOUT) -> dict:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(graph.invoke, state)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            _api_logger.warning("Graph invoke timed out after %ss", timeout)
            raise GraphTimeoutError(timeout) from None


def _extract_last_message(result: dict[str, Any]) -> str:
    messages = result.get("messages", [])
    return messages[-1].get("content", "") if messages else ""


def _extract_response(result: dict[str, Any], session_id: str) -> PlanResponse:
    return PlanResponse(
        status=result.get("status", "unknown"),
        message=_extract_last_message(result),
        itinerary=result.get("final_itinerary"),
        session_id=session_id,
    )


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@app.get("/diagnostics")
def diagnostics(request: Request):
    _check_diagnostics_access(request)

    from app.adapters.tool_factory import describe_active_tools
    from app.infrastructure.cache import poi_cache, route_cache, weather_cache
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
            "backend": getattr(store, "backend", "unknown"),
            "active": store.active_count,
        },
    }


@app.post("/plan", response_model=PlanResponse)
def plan(req: PlanRequest, request: Request):
    _check_api_access(request)

    session_id = str(uuid.uuid4())[:8]
    state = make_initial_state()
    state["messages"].append({"role": "user", "content": req.message})

    try:
        graph = _get_graph()
        result = _invoke_with_timeout(graph, state)
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

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_extract_last_message(result) or "无法生成可执行行程，请调整需求后重试",
        )

    store.save(session_id, result)
    return _extract_response(result, session_id)


@app.post("/chat", response_model=PlanResponse)
def chat(req: ChatRequest, request: Request):
    _check_api_access(request)

    session_id = req.session_id
    state = store.get(session_id)
    if state is None:
        state = make_initial_state()

    state["messages"].append({"role": "user", "content": req.message})

    if state.get("status") == "clarifying":
        merge_result = merge_user_update_node(state)
        state.update(merge_result)

    try:
        graph = _get_graph()
        result = _invoke_with_timeout(graph, state)
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

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_extract_last_message(result) or "无法继续该会话，请调整需求后重试",
        )

    store.save(session_id, result)
    return _extract_response(result, session_id)


def _safe_log_exception(context: str, exc: Exception) -> None:
    try:
        from app.security.key_manager import get_key_manager

        km = get_key_manager()
        safe_msg = km.scrub_text(str(exc))
        _api_logger.error("%s: %s", context, safe_msg)
    except Exception:
        _api_logger.error("%s: [exception details redacted]", context)
