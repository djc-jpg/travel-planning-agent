"""Backward-compatible wrapper for requirements parsing."""

from app.parsing.requirements import FIELD_LABELS, OPTIONAL_WITH_DEFAULTS, REQUIRED_FIELDS, check_missing

__all__ = ["REQUIRED_FIELDS", "OPTIONAL_WITH_DEFAULTS", "FIELD_LABELS", "check_missing"]

