"""LLM adapter tests. Uses a stub client — no network.
Pins request shape per provider and checks failure paths fall back offline.
"""

from __future__ import annotations

import pytest

from app.analysis.llm_adapter import LLMAdapter, build_prompt, offline_summary
from app.core.config import Settings

CLUSTERS = [
    {
        "service": "checkout",
        "alert_count": 3,
        "severities": ["critical", "warning"],
        "summary": "latency spike on 10.4.2.9; pool saturation",
    },
    {
        "service": "payments",
        "alert_count": 1,
        "severities": ["critical"],
        "summary": "gateway timeout",
    },
]
DETERMINISTIC = "Incident detected across 2 service cluster(s)."


class StubResponse:
    def __init__(self, status_code=200, payload=None, text="", raise_on_json=False):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self._raise_on_json = raise_on_json

    def json(self):
        if self._raise_on_json:
            raise ValueError("not json")
        return self._payload


class StubClient:
    """Records calls and replays a queue of responses."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.closed = False

    def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        result = self._responses.pop(0) if self._responses else StubResponse()
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        self.closed = True


def settings_for(**overrides) -> Settings:
    base = {
        "enable_llm": True,
        "llm_provider": "openai",
        "llm_model": "test-model",
        "llm_api_key": "test-key",
        "llm_max_retries": 0,
        "llm_redact": True,
    }
    base.update(overrides)
    return Settings(**base)


def openai_ok(content="LLM narrative."):
    return StubResponse(payload={"choices": [{"message": {"content": content}}]})


# -- offline provider --------------------------------------------------------


def test_offline_summary_names_the_worst_service_and_total():
    text = offline_summary(CLUSTERS, DETERMINISTIC)

    assert "checkout" in text
    assert "4 alert(s)" in text
    assert "Critical severity is present" in text


def test_offline_summary_passes_through_without_clusters():
    assert offline_summary([], DETERMINISTIC) == DETERMINISTIC


@pytest.mark.parametrize("provider", ["offline", "mock", "none", ""])
def test_offline_like_providers_never_touch_the_network(provider):
    client = StubClient()
    adapter = LLMAdapter(settings=settings_for(llm_provider=provider), client=client)

    result = adapter.summarize(CLUSTERS, DETERMINISTIC)

    assert client.calls == []
    assert "checkout" in result


def test_unknown_provider_falls_back_instead_of_raising():
    client = StubClient()
    adapter = LLMAdapter(settings=settings_for(llm_provider="hal9000"), client=client)

    result = adapter.summarize(CLUSTERS, DETERMINISTIC)

    assert client.calls == []
    assert "checkout" in result


# -- prompt ------------------------------------------------------------------


def test_prompt_orders_clusters_worst_first():
    prompt = build_prompt(
        [{"service": "quiet", "alert_count": 1}, {"service": "loud", "alert_count": 9}],
        DETERMINISTIC,
    )

    assert prompt.index("service=loud") < prompt.index("service=quiet")


# -- openai provider ---------------------------------------------------------


def test_openai_request_shape_and_auth_header():
    client = StubClient(openai_ok())
    adapter = LLMAdapter(settings=settings_for(), client=client)

    result = adapter.summarize(CLUSTERS, DETERMINISTIC)

    assert result == "LLM narrative."
    call = client.calls[0]
    assert call["url"] == "https://api.openai.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert call["json"]["model"] == "test-model"
    assert [m["role"] for m in call["json"]["messages"]] == ["system", "user"]


def test_openai_base_url_is_overridable_for_self_hosted_endpoints():
    client = StubClient(openai_ok())
    adapter = LLMAdapter(
        settings=settings_for(llm_base_url="http://vllm.internal:8000/v1/"), client=client
    )

    adapter.summarize(CLUSTERS, DETERMINISTIC)

    assert client.calls[0]["url"] == "http://vllm.internal:8000/v1/chat/completions"


def test_missing_api_key_degrades_to_offline():
    client = StubClient(openai_ok())
    adapter = LLMAdapter(settings=settings_for(llm_api_key=None), client=client)

    result = adapter.summarize(CLUSTERS, DETERMINISTIC)

    assert client.calls == []
    assert "checkout" in result


def test_prompt_is_redacted_before_leaving_the_process():
    client = StubClient(openai_ok())
    adapter = LLMAdapter(settings=settings_for(), client=client)

    adapter.summarize(CLUSTERS, DETERMINISTIC)

    sent = client.calls[0]["json"]["messages"][1]["content"]
    assert "10.4.2.9" not in sent
    assert "[IP]" in sent


def test_redaction_can_be_disabled():
    client = StubClient(openai_ok())
    adapter = LLMAdapter(settings=settings_for(llm_redact=False), client=client)

    adapter.summarize(CLUSTERS, DETERMINISTIC)

    assert "10.4.2.9" in client.calls[0]["json"]["messages"][1]["content"]


# -- ollama provider ---------------------------------------------------------


def test_ollama_request_shape_defaults_to_localhost():
    client = StubClient(StubResponse(payload={"message": {"content": "Local narrative."}}))
    adapter = LLMAdapter(
        settings=settings_for(llm_provider="ollama", llm_api_key=None), client=client
    )

    result = adapter.summarize(CLUSTERS, DETERMINISTIC)

    assert result == "Local narrative."
    call = client.calls[0]
    assert call["url"] == "http://localhost:11434/api/chat"
    assert call["json"]["stream"] is False
    assert "Authorization" not in call["headers"]


# -- failure handling --------------------------------------------------------


def test_http_error_degrades_to_offline_summary():
    client = StubClient(StubResponse(status_code=500, text="boom"))
    adapter = LLMAdapter(settings=settings_for(), client=client)

    result = adapter.summarize(CLUSTERS, DETERMINISTIC)

    assert "checkout" in result
    assert "without an LLM" in result


def test_transport_exception_degrades_to_offline_summary():
    client = StubClient(ConnectionError("no route to host"))
    adapter = LLMAdapter(settings=settings_for(), client=client)

    assert "checkout" in adapter.summarize(CLUSTERS, DETERMINISTIC)


def test_non_json_body_degrades_to_offline_summary():
    client = StubClient(StubResponse(raise_on_json=True))
    adapter = LLMAdapter(settings=settings_for(), client=client)

    assert "checkout" in adapter.summarize(CLUSTERS, DETERMINISTIC)


def test_unexpected_response_shape_degrades_to_offline_summary():
    client = StubClient(StubResponse(payload={"unexpected": True}))
    adapter = LLMAdapter(settings=settings_for(), client=client)

    assert "checkout" in adapter.summarize(CLUSTERS, DETERMINISTIC)


def test_empty_completion_degrades_to_offline_summary():
    client = StubClient(openai_ok(content="   "))
    adapter = LLMAdapter(settings=settings_for(), client=client)

    assert "checkout" in adapter.summarize(CLUSTERS, DETERMINISTIC)


def test_retryable_status_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.analysis.llm_adapter.time.sleep", lambda _: None)
    client = StubClient(StubResponse(status_code=503, text="unavailable"), openai_ok())
    adapter = LLMAdapter(settings=settings_for(llm_max_retries=1), client=client)

    result = adapter.summarize(CLUSTERS, DETERMINISTIC)

    assert result == "LLM narrative."
    assert len(client.calls) == 2


def test_non_retryable_status_is_not_retried(monkeypatch):
    """A 401 will not fix itself; retrying only delays the incident summary."""
    monkeypatch.setattr("app.analysis.llm_adapter.time.sleep", lambda _: None)
    client = StubClient(StubResponse(status_code=401, text="bad key"), openai_ok())
    adapter = LLMAdapter(settings=settings_for(llm_max_retries=3), client=client)

    result = adapter.summarize(CLUSTERS, DETERMINISTIC)

    assert len(client.calls) == 1
    assert "checkout" in result
