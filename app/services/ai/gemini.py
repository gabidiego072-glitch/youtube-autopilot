"""Gemini (Google AI Studio) implementation of `AIProvider`: the free option.

Uses the REST `generateContent` endpoint with JSON output constrained by the step's JSON Schema.
The free tier has per-minute and per-day request limits (see your quota in AI Studio). Per-minute
limits are waited out here; when the daily quota is used up the step fails with a clear message and
the run can be resumed the next day (`autopilot.py resume <run_id>`). Nothing is ever charged.

Note: on the free tier Google may use prompts and answers to improve its products. This project only
sends public-knowledge material (ideas, scripts, fact checks), never credentials or personal data.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import IntegrationNotConfiguredError, ProviderError
from app.services.ai.base import GenerationResult

logger = logging.getLogger(__name__)

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
MAX_RATE_WAITS = 2  # per model (retries also use free quota); then the next free model is tried
MAX_TRANSPORT_RETRIES = 2
MAX_WAIT_SECONDS = 90
BLOCKED = {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "RECITATION"}


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        settings: Settings,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not settings.gemini_configured:
            raise IntegrationNotConfiguredError(
                "Gemini is not configured. Create a free key at aistudio.google.com and set GEMINI_API_KEY."
            )
        self._key = settings.gemini_api_key.get_secret_value()
        self.model = settings.gemini_model
        self._max_tokens = settings.gemini_max_tokens
        self._http = http or httpx.Client(timeout=httpx.Timeout(settings.gemini_timeout_seconds, connect=20.0))
        self._sleep = sleep
        self._active: str | None = None
        self._configured_fallbacks = [m.strip() for m in settings.gemini_fallback_models.split(",") if m.strip()]
        self._fallback_cache: list[str] | None = None
        self._busy: set[str] = set()
        self._exhausted: set[str] = set()

    def __repr__(self) -> str:  # never leak the key
        return f"GeminiProvider(model={self.model!r})"

    # --- public -------------------------------------------------------------------------
    def generate_json(self, *, system: str, prompt: str, schema: dict[str, Any]) -> GenerationResult:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
                "maxOutputTokens": self._max_tokens,
            },
        }
        last: ProviderError | None = None
        for model in self._candidates():
            try:
                data = self._generate(body, schema, prompt, model)
            except _ModelUnavailable as exc:
                logger.warning("gemini model %s unavailable (%s); trying another free model", model, exc.message)
                (self._exhausted if exc.daily else self._busy).add(model)
                last = exc
                continue
            self._active = model  # stick to the model that answered for the rest of the run
            return self._result(data)
        if last is not None and last.daily:
            raise ProviderError(
                "Gemini's free daily quota is used up on every available model. Nothing was charged; "
                "resume the run tomorrow (it continues from this step)."
            )
        detail = last.message if last is not None else "no compatible fallback model was discovered"
        raise ProviderError(f"No available Gemini model could complete this request. Last error: {detail}")

    def _generate(self, body: dict, schema: dict, prompt: str, model: str) -> dict:
        try:
            return self._post(body, model)
        except _SchemaRejected:
            # Very large schemas can exceed the constrained-decoding limits: fall back to plain JSON
            # mode with the schema in the prompt. The pipeline validates every answer anyway.
            logger.warning("gemini rejected the JSON schema; retrying with the schema in the prompt")
            relaxed = json.loads(json.dumps(body))
            relaxed["generationConfig"].pop("responseJsonSchema")
            relaxed["contents"][0]["parts"][0]["text"] = (
                f"{prompt}\n\nAnswer with ONE JSON object that matches this JSON Schema exactly:\n"
                + json.dumps(schema, ensure_ascii=False)
            )
            return self._post(relaxed, model)

    def _candidates(self):
        """Model that last answered, GEMINI_MODEL, then free fallbacks (looked up only if needed).
        Models out of daily quota are skipped for the rest of the run; busy ones are tried last."""
        tried: set[str] = set()

        def fresh(models):
            for model in models:
                if model and model not in tried and model not in self._exhausted and model not in self._busy:
                    tried.add(model)
                    yield model

        yield from fresh((self._active, self.model))
        yield from fresh(self._fallbacks())
        for model in list(self._busy):  # one more chance for models that were only busy
            if model not in tried and model not in self._exhausted:
                tried.add(model)
                yield model

    def _fallbacks(self) -> list[str]:
        if self._fallback_cache is None:
            # Preserve the owner's explicit preference order, then append every other
            # compatible model discovered for this key. A short manual list must never
            # disable automatic discovery of additional models.
            discovered: list[str] = []
            try:
                discovered = pick_fallbacks(self.list_models(), self.model)
            except ProviderError as exc:
                logger.warning("Could not discover Gemini fallback models: %s", exc.message)
            combined = [*self._configured_fallbacks, *discovered]
            self._fallback_cache = list(dict.fromkeys(m for m in combined if m and m != self.model))
            logger.info("Gemini fallback models available: %s", self._fallback_cache)
        return self._fallback_cache

    def list_models(self) -> list[str]:
        """Models this key can call with generateContent (used by `autopilot.py ai-check`)."""
        # The API paginates this endpoint. Fetch all pages so a key with many enabled
        # models does not silently miss alternatives beyond the first page.
        found: set[str] = set()
        page_token: str | None = None
        for _ in range(10):  # defensive cap; 1,000 models is far beyond the current catalog
            params: dict[str, Any] = {"pageSize": 100}
            if page_token:
                params["pageToken"] = page_token
            response = self._request("GET", f"{API_ROOT}/models", params=params)
            if response.status_code != 200:
                raise ProviderError(f"Gemini API error: {_error(response)}")
            payload = response.json()
            found.update(
                m["name"].removeprefix("models/")
                for m in payload.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            )
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return sorted(found)

    # --- internals ----------------------------------------------------------------------
    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            return self._http.request(method, url, headers={"x-goog-api-key": self._key}, **kwargs)
        except httpx.TransportError as exc:
            raise ProviderError("Could not reach the Gemini API.") from exc

    def _post(self, body: dict, model: str) -> dict:
        """Streams the answer (server-sent events): long generations keep the connection alive
        instead of waiting minutes in silence, which proxies and load balancers cut."""
        url = f"{API_ROOT}/models/{model}:streamGenerateContent"
        transport_failures = 0
        for attempt in range(MAX_RATE_WAITS + 1):
            try:
                with self._http.stream(
                    "POST", url, params={"alt": "sse"}, json=body, headers={"x-goog-api-key": self._key}
                ) as response:
                    if response.status_code == 200:
                        return _merge_stream(response.iter_lines())
                    response.read()
            except httpx.TransportError as exc:
                transport_failures += 1
                if transport_failures > MAX_TRANSPORT_RETRIES:
                    raise ProviderError(f"Could not reach the Gemini API ({type(exc).__name__}).") from exc
                logger.info("gemini connection problem (%s), retrying", type(exc).__name__)
                self._sleep(10 * transport_failures)
                continue
            detail = _error(response)
            if response.status_code == 400 and "schema" in detail.lower():
                raise _SchemaRejected(detail)
            if response.status_code == 404:
                # Not available to this key: another model may still work. This is not a
                # daily-quota error, so do not report it as if the user's quota were exhausted.
                raise _ModelUnavailable(
                    f"model '{model}' not found for this key (run ai-check to list the available ones)"
                )
            if response.status_code in (401, 403):
                raise IntegrationNotConfiguredError(f"Gemini rejected the API key: {detail}")
            if response.status_code == 429 and _is_daily(response):
                raise _ModelUnavailable(f"daily free quota used up: {detail}", daily=True)
            if response.status_code in (429, 500, 503):
                if attempt >= MAX_RATE_WAITS:
                    raise _ModelUnavailable(detail)
                wait = _retry_delay(response) or min(MAX_WAIT_SECONDS, 5 * 2**attempt)
                logger.info("gemini %s on %s, waiting %.0fs", response.status_code, model, wait)
                self._sleep(min(MAX_WAIT_SECONDS, wait))
                continue
            raise ProviderError(f"Gemini API error: {detail}")
        raise _ModelUnavailable("still rate-limited")  # pragma: no cover

    def _result(self, data: dict) -> GenerationResult:
        block = data.get("promptFeedback", {}).get("blockReason")
        if block:
            raise ProviderError(f"Gemini blocked the prompt ({block}).")
        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderError("Gemini returned no answer.")
        candidate = candidates[0]
        reason = candidate.get("finishReason")
        if reason == "MAX_TOKENS":
            raise ProviderError("Gemini output was truncated (raise GEMINI_MAX_TOKENS).")
        if reason in BLOCKED:
            raise ProviderError(f"Gemini stopped the answer ({reason}).")
        text = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", []) if not p.get("thought"))
        try:
            parsed = json.loads(_strip_fences(text))
        except json.JSONDecodeError as exc:
            raise ProviderError("Gemini returned invalid JSON.") from exc
        if not isinstance(parsed, dict):
            raise ProviderError("Gemini returned JSON that is not an object.")
        meta = data.get("usageMetadata", {})
        usage = {
            "input_tokens": int(meta.get("promptTokenCount", 0)),
            "output_tokens": int(meta.get("candidatesTokenCount", 0)) + int(meta.get("thoughtsTokenCount", 0)),
        }
        model = data.get("modelVersion") or self.model
        logger.info("gemini generation model=%s usage=%s", model, usage)
        return GenerationResult(data=parsed, provider=self.name, model=model, usage=usage)


class _SchemaRejected(Exception):
    pass


class _ModelUnavailable(ProviderError):
    """Overloaded or out of free quota: worth trying another model."""

    def __init__(self, message: str, daily: bool = False) -> None:
        super().__init__(message)
        self.daily = daily


SKIP_MODEL_WORDS = (
    "image",
    "tts",
    "audio",
    "live",
    "embedding",
    "vision",
    "robotics",
    "computer-use",
    "native",
    "omni",
    "transcribe",
    "latest",  # omni: no free tier; '-latest' aliases point at the busiest model
)


def pick_fallbacks(models: list[str], primary: str, limit: int = 12) -> list[str]:
    """Prefer other text Flash models, then Pro models; stable before preview, newest first."""
    usable = [
        m for m in models
        if m != primary
        and any(kind in m for kind in ("flash", "pro"))
        and not any(word in m for word in SKIP_MODEL_WORDS)
    ]

    def rank(name: str):
        # Keep fast/cheap Flash choices ahead of Pro, while allowing Pro to rescue a
        # request when all Flash variants are overloaded or out of quota.
        family = 0 if "flash" in name else 1
        preview = "preview" in name or "exp" in name
        lite = "lite" in name
        return (family, preview, lite, [-ord(c) for c in name])

    return sorted(usable, key=rank)[:limit]


def _error(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
    except ValueError:
        return f"HTTP {response.status_code}"
    return f"HTTP {response.status_code} {error.get('status', '')} {error.get('message', '')}".strip()


def _details(response: httpx.Response) -> list[dict]:
    try:
        return response.json().get("error", {}).get("details", []) or []
    except ValueError:
        return []


def _is_daily(response: httpx.Response) -> bool:
    for detail in _details(response):
        for violation in detail.get("violations", []) or []:
            if "PerDay" in (violation.get("quotaId", "") + violation.get("quotaMetric", "")):
                return True
    return "per day" in _error(response).lower()


def _retry_delay(response: httpx.Response) -> float | None:
    for detail in _details(response):
        delay = detail.get("retryDelay")
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return float(delay[:-1]) + 1
            except ValueError:
                return None
    return None


def _merge_stream(lines) -> dict:
    """Join streamed chunks into one generateContent-shaped answer."""
    texts, merged = [], {}
    for line in lines:
        if not line.startswith("data:"):
            continue
        chunk = json.loads(line[5:].strip())
        if "error" in chunk:
            raise ProviderError(f"Gemini API error: {chunk['error'].get('message', chunk['error'])}")
        for key in ("promptFeedback", "usageMetadata", "modelVersion"):
            if key in chunk:
                merged[key] = chunk[key]
        for candidate in chunk.get("candidates", [])[:1]:
            for part in candidate.get("content", {}).get("parts", []):
                if part.get("text") and not part.get("thought"):
                    texts.append(part["text"])
            if candidate.get("finishReason"):
                merged["finishReason"] = candidate["finishReason"]
    if not texts and "finishReason" not in merged:
        return {key: value for key, value in merged.items() if key != "finishReason"}
    merged["candidates"] = [
        {"content": {"parts": [{"text": "".join(texts)}]}, "finishReason": merged.pop("finishReason", None)}
    ]
    return merged


def _strip_fences(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return (match.group(1) if match else text).strip()
