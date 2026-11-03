"""Gemini provider against a mocked API (no network, no key)."""

import json

import httpx
import pytest

from app.core.errors import IntegrationNotConfiguredError, ProviderError
from app.services.ai.factory import get_ai_provider
from app.services.ai.gemini import GeminiProvider
from tests.conftest import make_settings

SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def _provider(handler, waits=None):
    return GeminiProvider(
        make_settings(gemini_api_key="key-123", gemini_model="gemini-test"),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=(waits.append if waits is not None else lambda _: None),
    )


def _answer(text, reason="STOP"):
    """A streamed answer: the text arrives in two chunks, usage and finish reason in the last one."""
    half = len(text) // 2
    chunks = [
        {"candidates": [{"content": {"parts": [{"text": "thinking", "thought": True}, {"text": text[:half]}]}}]},
        {
            "candidates": [{"content": {"parts": [{"text": text[half:]}]}, "finishReason": reason}],
            "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30, "thoughtsTokenCount": 50},
            "modelVersion": "gemini-test-001",
        },
    ]
    body = "".join(f"data: {json.dumps(c)}\r\n\r\n" for c in chunks)
    return httpx.Response(200, content=body.encode(), headers={"Content-Type": "text/event-stream"})


def test_structured_json_request_and_usage():
    seen = []

    def handler(request):
        seen.append(request)
        return _answer('{"ok": true}')

    result = _provider(handler).generate_json(system="sys", prompt="hola", schema=SCHEMA)
    assert result.data == {"ok": True} and result.provider == "gemini" and result.model == "gemini-test-001"
    assert result.usage == {"input_tokens": 120, "output_tokens": 80}
    request = seen[0]
    assert request.url.path == "/v1beta/models/gemini-test:streamGenerateContent"
    assert request.url.params["alt"] == "sse"
    assert request.headers["x-goog-api-key"] == "key-123" and "key=" not in str(request.url)
    body = json.loads(request.content)
    assert body["systemInstruction"]["parts"][0]["text"] == "sys"
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseJsonSchema"] == SCHEMA


def test_per_minute_limit_is_waited_out():
    calls, waits = [], []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(
                429,
                json={
                    "error": {
                        "status": "RESOURCE_EXHAUSTED",
                        "message": "rate",
                        "details": [
                            {"violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
                            {"retryDelay": "12s"},
                        ],
                    }
                },
            )
        return _answer('{"ok": true}')

    assert _provider(handler, waits).generate_json(system="s", prompt="p", schema=SCHEMA).data == {"ok": True}
    assert waits == [13.0]


def test_daily_quota_stops_with_a_clear_message():
    def handler(request):
        return httpx.Response(
            429,
            json={
                "error": {
                    "status": "RESOURCE_EXHAUSTED",
                    "message": "quota",
                    "details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}],
                }
            },
        )

    with pytest.raises(ProviderError, match="free daily quota"):
        _provider(handler).generate_json(system="s", prompt="p", schema=SCHEMA)


def test_schema_too_complex_falls_back_to_schema_in_prompt():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        if len(bodies) == 1:
            return httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT", "message": "schema too complex"}})
        return _answer('```json\n{"ok": false}\n```')

    result = _provider(handler).generate_json(system="s", prompt="p", schema=SCHEMA)
    assert result.data == {"ok": False}
    assert "responseJsonSchema" not in bodies[1]["generationConfig"]
    assert "JSON Schema" in bodies[1]["contents"][0]["parts"][0]["text"]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_answer('{"ok": tr', reason="MAX_TOKENS"), "truncated"),
        (_answer("", reason="SAFETY"), "SAFETY"),
        (httpx.Response(200, content=b'data: {"promptFeedback": {"blockReason": "OTHER"}}\n\n'), "blocked"),
        (_answer("not json"), "invalid JSON"),
    ],
)
def test_bad_answers_are_errors_not_guesses(response, message):
    with pytest.raises(ProviderError, match=message):
        _provider(lambda r: response).generate_json(system="s", prompt="p", schema=SCHEMA)


def test_wrong_model_or_key_is_explained():
    with pytest.raises(IntegrationNotConfiguredError, match="ai-check"):
        _provider(lambda r: httpx.Response(404, json={"error": {"message": "not found"}})).generate_json(
            system="s", prompt="p", schema=SCHEMA
        )
    with pytest.raises(IntegrationNotConfiguredError, match="API key"):
        _provider(lambda r: httpx.Response(403, json={"error": {"message": "bad key"}})).generate_json(
            system="s", prompt="p", schema=SCHEMA
        )


def test_list_models_and_factory():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "models/gemini-a", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/embedding", "supportedGenerationMethods": ["embedContent"]},
                ]
            },
        )

    assert _provider(handler).list_models() == ["gemini-a"]
    with pytest.raises(IntegrationNotConfiguredError, match="aistudio.google.com"):
        get_ai_provider(make_settings())  # default provider is the free one
    assert get_ai_provider(make_settings(gemini_api_key="k")).name == "gemini"
    assert "key" not in repr(get_ai_provider(make_settings(gemini_api_key="secret-k")))


def test_dropped_connection_is_retried_then_explained():
    calls = []

    def flaky(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.RemoteProtocolError("server disconnected")
        return _answer('{"ok": true}')

    assert _provider(flaky).generate_json(system="s", prompt="p", schema=SCHEMA).data == {"ok": True}

    def dead(request):
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(ProviderError, match="ReadTimeout"):
        _provider(dead).generate_json(system="s", prompt="p", schema=SCHEMA)


def test_overloaded_model_switches_to_another_free_model():
    used = []

    def handler(request):
        path = request.url.path
        if path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": f"models/{n}", "supportedGenerationMethods": ["generateContent"]}
                        for n in ("gemini-test", "gemini-9-flash", "gemini-9-flash-lite", "gemini-9-flash-image")
                    ]
                },
            )
        model = path.split("/models/")[1].split(":")[0]
        used.append(model)
        if model == "gemini-test":
            return httpx.Response(503, json={"error": {"status": "UNAVAILABLE", "message": "high demand"}})
        return _answer('{"ok": true}')

    provider = _provider(handler)
    assert provider.generate_json(system="s", prompt="p", schema=SCHEMA).data == {"ok": True}
    assert used[-1] == "gemini-9-flash" and used.count("gemini-test") == 3  # 1 try + 2 waits, then switch
    used.clear()
    provider.generate_json(system="s", prompt="p", schema=SCHEMA)
    assert used == ["gemini-9-flash"]  # sticks to the model that works


def test_fallback_ranking():
    from app.services.ai.gemini import pick_fallbacks

    models = [
        "gemini-3.8-flash",
        "gemini-3.8-flash-lite",
        "gemini-3.5-flash",
        "gemini-4-flash-preview",
        "gemini-3.8-flash-image",
        "gemini-3.8-pro",
    ]
    assert pick_fallbacks(models, "gemini-3.8-flash") == [
        "gemini-3.5-flash",
        "gemini-3.8-flash-lite",
        "gemini-4-flash-preview",
    ]
