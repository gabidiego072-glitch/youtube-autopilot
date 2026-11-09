"""Kokoro narrators: language per voice, experiment voices per channel language, a real synthesis when installed."""

from pathlib import Path

import pytest

from app.services.experiments import VOICES, dimensions
from app.services.voice.kokoro import KokoroTTS, language_code


def test_kokoro_voices_are_the_ones_tried_and_speak_the_channel_language():
    assert all(VOICES[v].engine == "kokoro" for v in dimensions("es")["voice"] + dimensions("en")["voice"])
    assert language_code("em_alex") == "es" and language_code("am_onyx") == "en-us"
    assert language_code("bm_george") == "en-gb"
    assert all(VOICES[v].explore is False for v in ("davefx", "norman_us"))  # old videos still resolve


MODELS = Path("models/kokoro")


@pytest.mark.skipif(not KokoroTTS(MODELS, "em_alex").is_available(), reason="Kokoro model not installed")
def test_kokoro_speaks_spanish(tmp_path):
    out = KokoroTTS(MODELS, "em_alex").synthesize("¿Qué pasaría si todos fueran zombis menos tú?", tmp_path / "a.wav")
    assert out.is_file() and out.stat().st_size > 20_000
