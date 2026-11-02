import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.services.ai.base import AIProvider
from app.services.ai.factory import get_ai_provider
from app.services.rendering.ffmpeg import FFmpeg
from app.services.research.wikipedia import WikipediaClient
from app.services.visuals.providers import ImageProvider, get_image_provider
from app.services.voice.piper import PiperTTS

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[Session, Depends(get_db)]


def require_api_key(settings: SettingsDep, x_api_key: Annotated[str | None, Header()] = None) -> None:
    if settings.api_key is None:
        return
    expected = settings.api_key.get_secret_value()
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-Key.")


def provide_ai(settings: SettingsDep) -> AIProvider:
    return get_ai_provider(settings)


def provide_ffmpeg(settings: SettingsDep) -> FFmpeg:
    return FFmpeg(settings.ffmpeg_binary, settings.ffprobe_binary)


def provide_wikipedia(settings: SettingsDep) -> WikipediaClient | None:
    if not settings.research_enabled:
        return None
    return WikipediaClient(settings.wikipedia_language, settings.wikipedia_user_agent)


def provide_image_provider(settings: SettingsDep) -> ImageProvider:
    return get_image_provider(settings)


def provide_tts(settings: SettingsDep) -> PiperTTS:
    return PiperTTS(settings.piper_binary, settings.piper_voice_model, settings.piper_length_scale)


AIProviderDep = Annotated[AIProvider, Depends(provide_ai)]
WikipediaDep = Annotated[WikipediaClient | None, Depends(provide_wikipedia)]
ImageProviderDep = Annotated[ImageProvider, Depends(provide_image_provider)]
TTSDep = Annotated[PiperTTS, Depends(provide_tts)]
FFmpegDep = Annotated[FFmpeg, Depends(provide_ffmpeg)]
