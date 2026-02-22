"""Lightweight trace context + span logging with W3C traceparent compatibility."""

from __future__ import annotations

import contextlib
import contextvars
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

_TRACE_HEX_LEN = 32
_SPAN_HEX_LEN = 16
_TRACEPARENT_RE = "00-{trace_id}-{span_id}-01"


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: str = ""


_current_trace: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar(
    "trip_agent_trace_ctx",
    default=None,
)


def _random_hex(size: int) -> str:
    return secrets.token_hex(max(1, size // 2))[:size]


def _is_hex(value: str, expected_len: int) -> bool:
    if len(value) != expected_len:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _new_trace_context(parent_span_id: str = "") -> TraceContext:
    return TraceContext(
        trace_id=_random_hex(_TRACE_HEX_LEN),
        span_id=_random_hex(_SPAN_HEX_LEN),
        parent_span_id=parent_span_id,
    )


def parse_traceparent(header_value: str | None) -> TraceContext | None:
    if not header_value:
        return None
    raw = str(header_value).strip()
    parts = raw.split("-")
    if len(parts) != 4:
        return None
    version, trace_id, parent_span_id, _flags = parts
    if version != "00":
        return None
    if not _is_hex(trace_id, _TRACE_HEX_LEN):
        return None
    if not _is_hex(parent_span_id, _SPAN_HEX_LEN):
        return None
    if parent_span_id == "0" * _SPAN_HEX_LEN:
        return None
    return TraceContext(
        trace_id=trace_id.lower(),
        span_id=_random_hex(_SPAN_HEX_LEN),
        parent_span_id=parent_span_id.lower(),
    )


def begin_request_trace(traceparent_header: str | None) -> tuple[TraceContext, contextvars.Token[TraceContext | None]]:
    incoming = parse_traceparent(traceparent_header)
    trace_ctx = incoming if incoming is not None else _new_trace_context()
    token = _current_trace.set(trace_ctx)
    return trace_ctx, token


def end_request_trace(token: contextvars.Token[TraceContext | None]) -> None:
    _current_trace.reset(token)


def get_current_trace() -> TraceContext | None:
    return _current_trace.get()


def get_current_trace_id(default: str = "") -> str:
    ctx = get_current_trace()
    return ctx.trace_id if ctx is not None else default


def build_traceparent_header(ctx: TraceContext | None = None) -> str:
    target = ctx or get_current_trace() or _new_trace_context()
    return _TRACEPARENT_RE.format(
        trace_id=target.trace_id,
        span_id=target.span_id,
    )


def _tracing_enabled() -> bool:
    raw = os.getenv("ENABLE_TRACING", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


@contextlib.contextmanager
def trace_span(name: str, *, logger: Any = None, **attributes: Any):
    """Emit lightweight span_start/span_end structured logs around a code block."""
    if not _tracing_enabled():
        yield
        return

    parent = get_current_trace()
    if parent is None:
        current = _new_trace_context()
    else:
        current = TraceContext(
            trace_id=parent.trace_id,
            span_id=_random_hex(_SPAN_HEX_LEN),
            parent_span_id=parent.span_id,
        )
    token = _current_trace.set(current)
    started = time.perf_counter()

    if logger is not None and hasattr(logger, "summary"):
        logger.summary(
            stage="tracing",
            event="span_start",
            span_name=name,
            trace_id=current.trace_id,
            span_id=current.span_id,
            parent_span_id=current.parent_span_id,
            attributes=attributes,
        )

    try:
        yield current
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
        if logger is not None and hasattr(logger, "summary"):
            logger.summary(
                stage="tracing",
                event="span_end",
                span_name=name,
                trace_id=current.trace_id,
                span_id=current.span_id,
                parent_span_id=current.parent_span_id,
                duration_ms=duration_ms,
                attributes=attributes,
            )
        _current_trace.reset(token)


__all__ = [
    "TraceContext",
    "begin_request_trace",
    "build_traceparent_header",
    "end_request_trace",
    "get_current_trace",
    "get_current_trace_id",
    "parse_traceparent",
    "trace_span",
]
