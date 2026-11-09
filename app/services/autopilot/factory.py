"""Builds the real services the pipeline uses from settings (no fakes)."""

import sys
from pathlib import Path

from app.core.config import Settings
from app.services.ai.factory import get_ai_provider
from app.services.autopilot.runner import Services
from app.services.experiments import VOICES
from app.services.rendering.blender import Blender
from app.services.rendering.ffmpeg import FFmpeg
from app.services.research.wikipedia import WikipediaClient
from app.services.trends.signals import collect_signals
from app.services.voice.piper import PiperTTS


def piper_binary(settings: Settings) -> str:
    venv_piper = Path(sys.executable).parent / "piper"
    return str(venv_piper) if settings.piper_binary == "piper" and venv_piper.is_file() else settings.piper_binary


def real_services(settings: Settings, log=print) -> Services:
    return Services(
        ai=get_ai_provider(settings),  # raises a clear error if the AI key is missing
        wiki=WikipediaClient(settings.wikipedia_language, settings.wikipedia_user_agent)
        if settings.research_enabled
        else None,
        tts=PiperTTS(piper_binary(settings), settings.piper_voice_model, settings.piper_length_scale),
        blender=Blender(settings.blender_binary, settings.blender_timeout_seconds),
        ffmpeg=FFmpeg(settings.ffmpeg_binary, settings.ffprobe_binary),
        settings=settings,
        log=log,
        trends=(lambda: collect_signals(settings)) if settings.trends_enabled else None,
        voices=lambda voice_id: voice_tts(settings, voice_id),
    )


def voice_tts(settings: Settings, voice_id: str) -> PiperTTS | None:
    """The narrator for an experiment voice, or None if its model is not installed."""
    voice = VOICES.get(voice_id)
    if voice is not None and voice.engine == "kokoro":
        from app.services.voice.kokoro import KokoroTTS

        tts = KokoroTTS(settings.kokoro_model_dir, voice.model, settings.kokoro_speed)
        return tts if tts.is_available() else None
    folder = settings.piper_voice_model.parent if settings.piper_voice_model else Path("models/voices")
    if voice is None or not (folder / voice.model).is_file():
        return None
    return PiperTTS(piper_binary(settings), folder / voice.model, settings.piper_length_scale, voice.speaker)


def preflight(settings: Settings) -> list[str]:
    """What is missing before an unattended run can succeed."""
    problems = []
    if not settings.ai_configured:
        key = "GEMINI_API_KEY" if settings.ai_provider == "gemini" else "ANTHROPIC_API_KEY"
        problems.append(f"{key} is not set (ideas, research, scripts, fact-check, storyboard, metadata).")
    if not PiperTTS(piper_binary(settings), settings.piper_voice_model).is_available():
        problems.append(
            "Piper voice not available (pip install piper-tts; scripts/install_voice.sh; PIPER_VOICE_MODEL)."
        )
    if not Blender(settings.blender_binary).is_available():
        problems.append("Blender not found (scripts/install_blender.sh; BLENDER_BINARY).")
    if not FFmpeg(settings.ffmpeg_binary, settings.ffprobe_binary).is_available():
        problems.append("FFmpeg/FFprobe not found.")
    return problems
