import base64

import httpx

from app.core.config import Settings
from app.services.ai.gemini_images import GeminiImages, ImageError

PNG = b"\x89PNG\r\n\x1a\nfake"


def _settings():
    return Settings(gemini_api_key="test-key", ai_provider="gemini")


def test_a_picture_is_taken_from_the_first_model_that_draws(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if "first" in request.url.path:
            return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota per day"}})
        data = base64.b64encode(PNG).decode()
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"inlineData": {"data": data}}]}}]})

    images = GeminiImages(
        _settings(),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        models=("first", "second"),
        sleep=lambda s: None,
    )
    assert images.draw("a cat", [PNG]) == PNG
    assert images.model == "second" and "first" in images.errors
    assert images.draw("a dog") == PNG and calls[-1].endswith("second:generateContent")  # sticks to what works
    assert "test-key" not in repr(images)


def test_no_model_draws():
    def handler(request):
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "no"}]}}]})

    images = GeminiImages(_settings(), http=httpx.Client(transport=httpx.MockTransport(handler)), models=("a",))
    try:
        images.draw("x")
    except ImageError as exc:
        assert "without a picture" in str(exc)
    else:
        raise AssertionError("expected ImageError")
