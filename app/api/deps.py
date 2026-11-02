import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.services.ai.base import AIProvider
from app.services.ai.factory import get_ai_provider
from app.services.rendering.ffmpeg import FFmpeg

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


AIProviderDep = Annotated[AIProvider, Depends(provide_ai)]
FFmpegDep = Annotated[FFmpeg, Depends(provide_ffmpeg)]
