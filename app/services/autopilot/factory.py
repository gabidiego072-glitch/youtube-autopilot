"""Builds the real services the pipeline uses from settings (no fakes)."""

import sys
from pathlib import Path

from app.core.config import Settings
from app.services.ai.factory import get_ai_provider
from app.services.autopilot.runner import Services
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
        ai=get_ai_provider(settings),  # raises a clear error if ANTHROPIC_API_KEY is missing
        wiki=WikipediaClient(settings.wikipedia_language, settings.wikipedia_user_agent)
        if settings.research_enabled
        else None,
        tts=PiperTTS(piper_binary(settings), settings.piper_voice_model, settings.piper_length_scale),
        blender=Blender(settings.blender_binary, settings.blender_timeout_seconds),
        ffmpeg=FFmpeg(settings.ffmpeg_binary, settings.ffprobe_binary),
        settings=settings,
        log=log,
        trends=(lambda: collect_signals(settings)) if settings.trends_enabled else None,
    )


def preflight(settings: Settings) -> list[str]:
    """What is missing before an unattended run can succeed."""
    problems = []
    if not settings.claude_configured:
        problems.append("ANTHROPIC_API_KEY is not set (ideas, research, scripts, fact-check, storyboard, metadata).")
    if not PiperTTS(piper_binary(settings), settings.piper_voice_model).is_available():
        problems.append(
            "Piper voice not available (pip install piper-tts; scripts/install_voice.sh; PIPER_VOICE_MODEL)."
        )
    if not Blender(settings.blender_binary).is_available():
        problems.append("Blender not found (scripts/install_blender.sh; BLENDER_BINARY).")
    if not FFmpeg(settings.ffmpeg_binary, settings.ffprobe_binary).is_available():
        problems.append("FFmpeg/FFprobe not found.")
    return problems
