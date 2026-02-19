"""Helpers for redacting sensitive values in logs and error strings."""

from __future__ import annotations

import re

_REDACTED = "***REDACTED***"

_QUERY_VALUE_RE = re.compile(
    r"(?i)(?P<prefix>\b(?:key|api[_-]?key|token|secret|signature|sig|password|passwd)\s*=\s*)(?P<value>[^&\s\"']+)"
)
_JSON_KV_RE = re.compile(
    r"(?i)(?P<prefix>(?:[\"']?(?:api[_-]?key|x-api-key|token|secret|signature|sig|password|passwd)[\"']?\s*[:=]\s*[\"']?))(?P<value>[^\"',\s}]+)"
)
_AUTH_HEADER_RE = re.compile(
    r"(?i)(?P<prefix>\bauthorization\s*:\s*(?:bearer|basic|token)\s+)(?P<value>[^\s,;]+)"
)
_X_API_KEY_HEADER_RE = re.compile(
    r"(?i)(?P<prefix>\bx-api-key\s*:\s*)(?P<value>[^\s,;]+)"
)
_BEARER_RE = re.compile(
    r"(?i)(?P<prefix>\bbearer\s+)(?P<value>[A-Za-z0-9._~+/=-]+)"
)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_DSN_CREDENTIAL_RE = re.compile(
    r"(?i)(?P<prefix>\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://)(?P<creds>[^@/\s]+)@"
)
_OPENAI_DASHSCOPE_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_GITHUB_TOKEN_RE = re.compile(r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")


def _replace_value(pattern: re.Pattern[str], text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return f"{match.group('prefix')}{_REDACTED}"

    return pattern.sub(repl, text)


def redact_sensitive(text: str) -> str:
    """Redact common secret patterns while preserving surrounding context."""
    if not text:
        return text

    redacted = str(text)

    value_patterns: tuple[re.Pattern[str], ...] = (
        _QUERY_VALUE_RE,
        _JSON_KV_RE,
        _AUTH_HEADER_RE,
        _X_API_KEY_HEADER_RE,
        _BEARER_RE,
    )
    for pattern in value_patterns:
        redacted = _replace_value(pattern, redacted)

    full_patterns: tuple[re.Pattern[str], ...] = (
        _JWT_RE,
        _OPENAI_DASHSCOPE_KEY_RE,
        _GITHUB_TOKEN_RE,
    )
    for pattern in full_patterns:
        redacted = pattern.sub(_REDACTED, redacted)

    redacted = _DSN_CREDENTIAL_RE.sub(rf"\g<prefix>{_REDACTED}@", redacted)
    return redacted


__all__ = ["redact_sensitive"]
