"""FastAPI 主应用 — 安全加固版"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import time
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.application.graph.workflow import compile_graph
from app.application.state_factory import make_initial_state
from app.agent.nodes.merge_user_update import merge_user_update_node
from app.api.schemas import ChatRequest, HealthResponse, PlanRequest, PlanResponse
from app.infrastructure.session_store import get_session_store

_api_logger = logging.getLogger("trip-agent.api")

load_dotenv()  # 自动加载 .env 文件

_GRAPH_TIMEOUT = int(os.getenv("GRAPH_TIMEOUT_SECONDS", "120"))

app = FastAPI(
    title="trip-agent",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "false").lower() == "true" else None,
    redoc_url=None,
)


# ── 安全中间件 ────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """注入安全响应头"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """简易请求频率限制（单进程内存版）"""

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self._max = max_requests
        self._window = window_seconds
        self._counters: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next):
        # 只限制 POST 接口
        if request.method != "POST":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        hits = self._counters.get(client_ip, [])
        # 清除过期记录
        hits = [t for t in hits if now - t < self._window]
        if len(hits) >= self._max:
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
            )
        hits.append(now)
        self._counters[client_ip] = hits
        return await call_next(request)


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    max_requests=int(os.getenv("RATE_LIMIT_MAX", "60")),
    window_seconds=int(os.getenv("RATE_LIMIT_WINDOW", "60")),
)

# CORS — 生产环境应限制 origins
_cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

store = get_session_store()

# ── Graph 缓存（避免每次请求重新编译） ────────────────
_compiled_graph = None


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = compile_graph()
    return _compiled_graph


def _invoke_with_timeout(graph, state: dict, timeout: int = _GRAPH_TIMEOUT) -> dict:
    """带超时保护的 graph.invoke 调用"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(graph.invoke, state)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            _api_logger.warning(f"Graph invoke timed out after {timeout}s")
            return {
                **state,
                "status": "error",
                "messages": state.get("messages", []) + [
                    {"role": "assistant", "content": f"规划超时（{timeout}秒），请简化需求后重试"}
                ],
            }


def _extract_response(result: dict[str, Any], session_id: str) -> PlanResponse:
    status = result.get("status", "unknown")
    messages = result.get("messages", [])
    last_msg = messages[-1].get("content", "") if messages else ""

    return PlanResponse(
        status=status,
        message=last_msg,
        itinerary=result.get("final_itinerary"),
        session_id=session_id,
    )


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@app.get("/diagnostics")
def diagnostics():
    """内部诊断接口 — 显示工具状态、缓存命中率、session 数（生产环境应加鉴权）"""
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
def plan(req: PlanRequest):
    """一次性规划：直接出行程或返回 clarifying"""
    session_id = str(uuid.uuid4())[:8]
    state = make_initial_state()
    state["messages"].append({"role": "user", "content": req.message})

    try:
        graph = _get_graph()
        result = _invoke_with_timeout(graph, state)
    except Exception as e:
        _safe_log_exception("plan endpoint error", e)
        return PlanResponse(
            status="error",
            message="规划过程出错，请稍后重试",
            itinerary=None,
            session_id=session_id,
        )

    store.save(session_id, result)
    return _extract_response(result, session_id)


@app.post("/chat", response_model=PlanResponse)
def chat(req: ChatRequest):
    """多轮对话：带 session_id 继续对话"""
    session_id = req.session_id
    state = store.get(session_id)

    if state is None:
        state = make_initial_state()

    state["messages"].append({"role": "user", "content": req.message})

    # 如果上次是 clarifying，先 merge
    if state.get("status") == "clarifying":
        merge_result = merge_user_update_node(state)
        state.update(merge_result)

    try:
        graph = _get_graph()
        result = _invoke_with_timeout(graph, state)
    except Exception as e:
        _safe_log_exception("chat endpoint error", e)
        return PlanResponse(
            status="error",
            message="对话处理出错，请稍后重试",
            itinerary=None,
            session_id=session_id,
        )

    store.save(session_id, result)
    return _extract_response(result, session_id)


def _safe_log_exception(context: str, exc: Exception) -> None:
    """脱敏后记录异常日志"""
    try:
        from app.security.key_manager import get_key_manager
        km = get_key_manager()
        safe_msg = km.scrub_text(str(exc))
        _api_logger.error(f"{context}: {safe_msg}")
    except Exception:
        _api_logger.error(f"{context}: [exception details redacted]")
