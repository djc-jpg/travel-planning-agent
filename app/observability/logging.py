"""Backward-compatible logging wrapper."""

from app.infrastructure.logging import StructuredLogger, get_logger

__all__ = ["StructuredLogger", "get_logger"]

