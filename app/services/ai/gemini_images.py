"""Illustrations made by Gemini's image models: one picture per narration line, all in one style.

Nov 15: the 3D engine only has a fixed set of places and objects, so even good videos showed what the voice says
in 3-4 scenes out of 9 ("the bridge snaps in half" became a generic street). A drawn picture per line shows
exactly what the line says. This module only talks to the API; the video is put together elsewhere.
"""

from __future__ import annotations

import base64
import logging
import time

import httpx

from app.core.config import Settings
from app.core.errors import IntegrationNotConfiguredError, ProviderError

logger = logging.getLogger(__name__)

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
# Tried in order; the first that answers with a picture is used for the rest of the run.
IMAGE_MODELS = (
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-lite-image",
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image",
)


class ImageError(ProviderError):
    pass


class GeminiImages:
    def __init__(
        self,
        settings: Settings,
        http: httpx.Client | None = None,
        models: tuple[str, ...] = IMAGE_MODELS,
        sleep=time.sleep,
    ) -> None:
        if not settings.gemini_configured:
            raise IntegrationNotConfiguredError("Gemini is not configured (GEMINI_API_KEY).")
        self._key = settings.gemini_api_key.get_secret_value()
        self._http = http or httpx.Client(timeout=httpx.Timeout(180.0, connect=20.0))
        self._models = list(models)
        self._sleep = sleep
        self.model: str | None = None
        self.errors: dict[str, str] = {}  # model -> why it did not give a picture (for the report)

    def __repr__(self) -> str:  # never leak the key
        return f"GeminiImages(model={self.model!r})"

    def draw(self, prompt: str, references: list[bytes] | None = None, aspect: str = "9:16") -> bytes:
        """A PNG/JPEG picture for the prompt. `references` are earlier pictures whose characters and style the
        new one must keep (the same companion in every scene)."""
        parts: list[dict] = [{"text": prompt}]
        for image in references or []:
            parts.append({"inlineData": {"mimeType": _mime(image), "data": base64.b64encode(image).decode()}})
        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}},
        }
        for model in ([self.model] if self.model else []) + [m for m in self._models if m != self.model]:
            if model in self.errors and model != self.model:
                continue
            picture = self._ask(model, body)
            if picture:
                self.model = model
                return picture
        raise ImageError(
            "No Gemini image model gave a picture: " + "; ".join(f"{k}: {v}" for k, v in self.errors.items())
        )

    def _ask(self, model: str, body: dict) -> bytes | None:
        url = f"{API_ROOT}/models/{model}:generateContent"
        for attempt in range(3):
            try:
                response = self._http.post(url, json=body, headers={"x-goog-api-key": self._key})
            except httpx.TransportError as exc:
                self.errors[model] = f"connection problem ({type(exc).__name__})"
                self._sleep(5 * (attempt + 1))
                continue
            if response.status_code == 200:
                picture = _picture(response.json())
                if picture:
                    self.errors.pop(model, None)
                    return picture
                self.errors[model] = "answered without a picture"
                return None
            self.errors[model] = _error(response)
            if response.status_code == 429 and attempt < 2 and "per day" not in self.errors[model].lower():
                self._sleep(30)  # per-minute limit: wait and try again
                continue
            if response.status_code in (500, 503) and attempt < 2:
                self._sleep(10)
                continue
            return None
        return None


def _picture(data: dict) -> bytes | None:
    for candidate in data.get("candidates", []) or []:
        for part in (candidate.get("content") or {}).get("parts", []) or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    return None


def _mime(image: bytes) -> str:
    return "image/jpeg" if image[:3] == b"\xff\xd8\xff" else "image/png"


def _error(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
    except ValueError:
        return f"HTTP {response.status_code}"
    return f"HTTP {response.status_code} {error.get('status', '')} {error.get('message', '')[:300]}".strip()
