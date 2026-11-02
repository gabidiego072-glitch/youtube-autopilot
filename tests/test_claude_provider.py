"""ClaudeProvider request/response handling, using a stub in place of the SDK client."""

import json
from types import SimpleNamespace

import pytest

from app.core.errors import IntegrationNotConfiguredError, ProviderError
from app.services.ai.claude import FALLBACK_BETA, ClaudeProvider
from tests.conftest import make_settings


class _Stream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


class _StubClient:
    def __init__(self, message):
        self.params = None
        outer = self

        class _Messages:
            def stream(self, **params):
                outer.params = params
                return _Stream(message)

        self.beta = SimpleNamespace(messages=_Messages())


def _message(text: str | None, stop_reason: str = "end_turn"):
    content = [SimpleNamespace(type="thinking", thinking="")]
    if text is not None:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
    )


def test_requires_api_key():
    with pytest.raises(IntegrationNotConfiguredError):
        ClaudeProvider(make_settings())


def test_builds_request_and_parses_json():
    client = _StubClient(_message(json.dumps({"ok": True})))
    provider = ClaudeProvider(make_settings(claude_effort="high"), client=client)
    result = provider.generate_json(system="sys", prompt="hi", schema={"type": "object"})
    assert result.data == {"ok": True}
    assert result.provider == "claude"
    assert client.params["model"] == "claude-opus-5-5"
    assert client.params["thinking"] == {"type": "adaptive"}
    assert client.params["output_config"]["effort"] == "high"
    assert client.params["output_config"]["format"]["type"] == "json_schema"
    assert client.params["betas"] == [FALLBACK_BETA]
    assert client.params["fallbacks"] == "default"


def test_fallbacks_can_be_disabled():
    client = _StubClient(_message("{}"))
    ClaudeProvider(make_settings(claude_server_fallbacks=False), client=client).generate_json(
        system="s", prompt="p", schema={}
    )
    assert "fallbacks" not in client.params and "betas" not in client.params


@pytest.mark.parametrize(
    ("message", "match"),
    [
        (_message(None, "refusal"), "declined"),
        (_message("{", "max_tokens"), "truncated"),
        (_message("not json"), "invalid JSON"),
        (_message(None), "no text"),
    ],
)
def test_error_paths(message, match):
    provider = ClaudeProvider(make_settings(), client=_StubClient(message))
    with pytest.raises(ProviderError, match=match):
        provider.generate_json(system="s", prompt="p", schema={})
