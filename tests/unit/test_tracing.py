from __future__ import annotations

from app.observability.tracing import (
    begin_request_trace,
    build_traceparent_header,
    end_request_trace,
    get_current_trace_id,
    parse_traceparent,
    trace_span,
)


class _DummyLogger:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def summary(self, **extra):
        self.rows.append(extra)


def test_parse_traceparent_and_build_roundtrip():
    parsed = parse_traceparent("00-0123456789abcdef0123456789abcdef-0123456789abcdef-01")
    assert parsed is not None
    assert parsed.trace_id == "0123456789abcdef0123456789abcdef"
    header = build_traceparent_header(parsed)
    assert header.startswith("00-0123456789abcdef0123456789abcdef-")


def test_begin_and_end_request_trace_context():
    ctx, token = begin_request_trace(None)
    assert get_current_trace_id() == ctx.trace_id
    end_request_trace(token)
    assert get_current_trace_id() == ""


def test_trace_span_emits_start_and_end_events():
    logger = _DummyLogger()
    ctx, token = begin_request_trace(None)
    try:
        with trace_span("unit_test_span", logger=logger, key="value"):
            assert get_current_trace_id() == ctx.trace_id
    finally:
        end_request_trace(token)

    assert len(logger.rows) == 2
    assert logger.rows[0]["event"] == "span_start"
    assert logger.rows[1]["event"] == "span_end"
    assert logger.rows[0]["span_name"] == "unit_test_span"
