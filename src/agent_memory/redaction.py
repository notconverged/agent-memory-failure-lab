from __future__ import annotations

import hashlib
import re

SECRET_PATTERNS = (
    re.compile(
        r"(?i)['\"]?(api[_-]?key|secret|token|password|passwd)['\"]?"
        r"\s*[:=]\s*(['\"]?)[^\s,'\"}]+\2"
    ),
    re.compile(r"\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)authorization:\s*(?:bearer|basic)\s+\S+"),
)


def redact_text(value: str, max_chars: int = 4_096) -> str:
    bounded = value[:max_chars]
    for pattern in SECRET_PATTERNS:
        bounded = pattern.sub("[REDACTED]", bounded)
    if len(value) > max_chars:
        bounded += "\n[TRUNCATED]"
    return bounded


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
