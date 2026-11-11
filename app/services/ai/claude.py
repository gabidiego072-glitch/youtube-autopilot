"""Claude (Anthropic) implementation of `AIProvider`."""

import json
import logging
from typing import Any

import anthropic

from app.core.config import Settings
from app.core.errors import IntegrationNotConfiguredError, ProviderError
from app.services.ai.base import GenerationResult

logger = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeProvider:
    name = "claude"

    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None) -> None:
        if client is None:
            if not settings.claude_configured:
                raise IntegrationNotConfiguredError(
                    "Claude is not configured. Set ANTHROPIC_API_KEY to enable AI generation."
                )
            client = anthropic.Anthropic(
                api_key=settings.anthropic_api_key.get_secret_value(),
                timeout=settings.claude_timeout_seconds,
            )
        self._client = client
        self.model = settings.claude_model
        self._effort = settings.claude_effort
        self._max_tokens = settings.claude_max_tokens
        self._fallbacks = settings.claude_server_fallbacks

    def generate_json(
        self, *, system: str, prompt: str, schema: dict[str, Any], images: list[bytes] | None = None
    ) -> GenerationResult:
        content: Any = prompt
        if images:
            content = [
                *(
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _b64(i)}}
                    for i in images
                ),
                {"type": "text", "text": prompt},
            ]
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": content}],
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": self._effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        }
        if self._fallbacks:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"

        try:
            # Streaming avoids HTTP timeouts on long generations (long-form scripts).
            with self._client.beta.messages.stream(**params) as stream:
                response = stream.get_final_message()
        except anthropic.RateLimitError as exc:
            raise ProviderError("Claude rate limit reached; retry later.") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"Claude API error ({exc.status_code}).") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("Could not reach the Claude API.") from exc

        if response.stop_reason == "refusal":
            raise ProviderError("Claude declined this request.")
        if response.stop_reason == "max_tokens":
            raise ProviderError("Claude output was truncated (CLAUDE_MAX_TOKENS too low).")

        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise ProviderError("Claude returned no text output.")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError("Claude returned invalid JSON.") from exc

        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        logger.info("claude generation model=%s usage=%s", response.model, usage)
        return GenerationResult(data=data, provider=self.name, model=response.model, usage=usage)


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode()
