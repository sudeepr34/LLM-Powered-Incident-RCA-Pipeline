"""Scrub identifiers from alert text before a prompt leaves the process.

Redacts IPs, emails, AWS keys, JWTs, UUIDs, hashes, and credential-shaped
``key=value`` pairs. On by default. For data that must not leave the host,
use the ``ollama`` provider or leave the LLM off.
"""

from __future__ import annotations

import re

# Order matters: the more specific credential patterns run before the generic
# long-token pattern so that a matched key is labelled as a key.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("[EMAIL]", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("[AWS_KEY]", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("[JWT]", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    (
        "[SECRET]",
        re.compile(
            r"(?i)\b(?:bearer|api[_-]?key|secret|password|passwd|token)\b\s*[:=]?\s*"
            r"[\"']?([A-Za-z0-9_\-./+=]{8,})[\"']?"
        ),
    ),
    ("[UUID]", re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b")),
    ("[IP]", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b(?::\d{1,5})?")),
    ("[HASH]", re.compile(r"\b[0-9a-fA-F]{32,}\b")),
)


def redact(text: str) -> str:
    """Replace identifiers and credential-shaped strings with labelled markers."""
    if not text:
        return text

    cleaned = text
    for label, pattern in _PATTERNS:
        if label == "[SECRET]":
            # Keep the key name, drop only the value, so the summary can still
            # say "an auth token was malformed" without carrying the token.
            cleaned = pattern.sub(
                lambda m: m.group(0).replace(m.group(1), "[SECRET]"), cleaned
            )
        else:
            cleaned = pattern.sub(label, cleaned)
    return cleaned


def redact_clusters(clusters: list[dict]) -> list[dict]:
    """Redact the free-text fields of each cluster, leaving structure intact."""
    redacted = []
    for cluster in clusters:
        copy = dict(cluster)
        for key in ("summary", "service"):
            if isinstance(copy.get(key), str):
                copy[key] = redact(copy[key])
        redacted.append(copy)
    return redacted
