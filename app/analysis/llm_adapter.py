"""LLM summarisation for incident analysis.

Providers:

- ``offline`` — deterministic, no network (default and fallback)
- ``openai`` — any OpenAI-compatible ``/chat/completions`` endpoint
  (OpenAI, Groq, OpenRouter, vLLM, LM Studio); set ``RCA_LLM_BASE_URL``
- ``ollama`` — local Ollama daemon

Any provider failure falls back to the offline summary and logs the reason.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.analysis.redaction import redact, redact_clusters
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an on-call site reliability engineer writing the opening summary "
    "of an incident review. Be concise and factual. Work only from the alert "
    "data provided; never invent metrics, timestamps, or causes. State the most "
    "likely blast radius and the single most probable failing component. "
    "Redaction markers such as [IP] or [SECRET] are intentional - do not "
    "speculate about what they contained. Reply with 3-5 sentences of prose, "
    "no headings and no bullet points."
)

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    """Raised when a provider cannot return a usable completion."""


def build_prompt(clusters: list[dict[str, Any]], incident_summary: str) -> str:
    """Render the cluster structure into a compact, stable prompt."""
    lines = [
        "Deterministic correlation output for the current incident:",
        "",
        f"Overview: {incident_summary}",
        "",
        "Affected service clusters, worst first:",
    ]
    ordered = sorted(clusters, key=lambda c: c.get("alert_count", 0), reverse=True)
    for cluster in ordered:
        severities = cluster.get("severities") or []
        lines.append(
            f"- service={cluster.get('service', 'unknown')} "
            f"alerts={cluster.get('alert_count', 0)} "
            f"severities={','.join(severities) if severities else 'unknown'}"
        )
        summary = cluster.get("summary")
        if summary:
            lines.append(f"  observed: {summary}")
    lines += ["", "Write the incident summary."]
    return "\n".join(lines)


def offline_summary(clusters: list[dict[str, Any]], incident_summary: str) -> str:
    """Deterministic narrative built from the cluster structure alone."""
    if not clusters:
        return incident_summary

    ordered = sorted(clusters, key=lambda c: c.get("alert_count", 0), reverse=True)
    primary = ordered[0]
    total = sum(c.get("alert_count", 0) for c in clusters)
    critical = [
        c.get("service", "unknown")
        for c in ordered
        if any("crit" in str(s).lower() for s in (c.get("severities") or []))
    ]

    parts = [
        f"{total} alert(s) correlated across {len(clusters)} service(s); "
        f"{primary.get('service', 'unknown')} is the likely origin with "
        f"{primary.get('alert_count', 0)} alert(s)."
    ]
    if critical:
        parts.append(f"Critical severity is present on: {', '.join(sorted(set(critical)))}.")
    if len(ordered) > 1:
        downstream = ", ".join(c.get("service", "unknown") for c in ordered[1:4])
        parts.append(f"Also alerting, possibly downstream: {downstream}.")
    parts.append("Generated without an LLM; treat service ordering as a starting point.")
    return " ".join(parts)


class LLMAdapter:
    """Turns correlated clusters into an incident narrative."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        settings: Settings | None = None,
        client: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = (provider or self.settings.llm_provider or "offline").strip().lower()
        self.model = model or self.settings.llm_model
        # Injected for tests; otherwise a client is created per call so the
        # adapter holds no sockets open between incidents.
        self._client = client

    # -- public API ----------------------------------------------------------

    def summarize(self, clusters: list[dict[str, Any]], incident_summary: str) -> str:
        """Return a narrative summary, degrading to the offline text on failure."""
        if self.provider in {"offline", "mock", "none", ""}:
            return offline_summary(clusters, incident_summary)

        if self.provider not in {"openai", "ollama"}:
            logger.warning(
                "Unknown LLM provider %r; using the offline summary", self.provider
            )
            return offline_summary(clusters, incident_summary)

        payload_clusters = (
            redact_clusters(clusters) if self.settings.llm_redact else clusters
        )
        summary_text = redact(incident_summary) if self.settings.llm_redact else incident_summary
        prompt = build_prompt(payload_clusters, summary_text)

        try:
            text = self._complete_with_retries(prompt)
        except LLMError as exc:
            logger.warning(
                "LLM provider %s failed (%s); falling back to the offline summary",
                self.provider,
                exc,
            )
            return offline_summary(clusters, incident_summary)

        cleaned = text.strip()
        if not cleaned:
            logger.warning("LLM provider %s returned empty text; using offline summary", self.provider)
            return offline_summary(clusters, incident_summary)
        return cleaned

    # -- provider plumbing ---------------------------------------------------

    def _complete_with_retries(self, prompt: str) -> str:
        attempts = max(1, self.settings.llm_max_retries + 1)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                return self._complete(prompt)
            except LLMError as exc:
                last_error = exc
                if attempt == attempts or not getattr(exc, "retryable", False):
                    break
                backoff = min(2.0 ** (attempt - 1), 8.0)
                logger.info(
                    "LLM attempt %d/%d failed (%s); retrying in %.1fs",
                    attempt,
                    attempts,
                    exc,
                    backoff,
                )
                time.sleep(backoff)

        raise LLMError(str(last_error) if last_error else "completion failed")

    def _http_client(self):
        if self._client is not None:
            return self._client
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise LLMError("httpx is not installed") from exc
        return httpx.Client(timeout=self.settings.llm_timeout_seconds)

    def _complete(self, prompt: str) -> str:
        if self.provider == "openai":
            url, headers, body, extract = self._openai_request(prompt)
        else:
            url, headers, body, extract = self._ollama_request(prompt)

        client = self._http_client()
        owns_client = self._client is None
        try:
            response = client.post(url, headers=headers, json=body)
        except Exception as exc:
            error = LLMError(f"request to {url} failed: {exc}")
            error.retryable = True  # type: ignore[attr-defined]
            raise error from exc
        finally:
            if owns_client:
                close = getattr(client, "close", None)
                if callable(close):
                    close()

        status = getattr(response, "status_code", 200)
        if status >= 400:
            error = LLMError(f"{self.provider} returned HTTP {status}: {self._body_text(response)}")
            error.retryable = status in RETRYABLE_STATUS  # type: ignore[attr-defined]
            raise error

        try:
            data = response.json()
        except Exception as exc:
            raise LLMError(f"{self.provider} returned a non-JSON body") from exc

        try:
            return extract(data)
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                f"unexpected {self.provider} response shape: {json.dumps(data)[:200]}"
            ) from exc

    def _openai_request(self, prompt: str):
        if not self.settings.llm_api_key:
            raise LLMError("RCA_LLM_API_KEY is not set")

        base = (self.settings.llm_base_url or "https://api.openai.com/v1").rstrip("/")
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.settings.llm_temperature,
            "max_tokens": self.settings.llm_max_tokens,
        }
        extract = lambda data: data["choices"][0]["message"]["content"]  # noqa: E731
        return f"{base}/chat/completions", headers, body, extract

    def _ollama_request(self, prompt: str):
        base = (self.settings.llm_base_url or "http://localhost:11434").rstrip("/")
        body = {
            "model": self.model or "llama3.1",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "temperature": self.settings.llm_temperature,
                "num_predict": self.settings.llm_max_tokens,
            },
        }
        extract = lambda data: data["message"]["content"]  # noqa: E731
        return f"{base}/api/chat", {"Content-Type": "application/json"}, body, extract

    @staticmethod
    def _body_text(response: Any) -> str:
        text = getattr(response, "text", "")
        return text[:200] if isinstance(text, str) else ""
