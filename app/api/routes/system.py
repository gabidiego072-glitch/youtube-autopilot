from fastapi import APIRouter

from app.api.deps import FFmpegDep, SettingsDep
from app.core.config import Settings
from app.schemas.system import IntegrationsStatus, IntegrationState
from app.services.rendering.ffmpeg import FFmpeg

router = APIRouter(prefix="/system", tags=["system"])


def integrations_status(settings: Settings, ffmpeg: FFmpeg) -> IntegrationsStatus:
    ffmpeg_version = ffmpeg.version()
    youtube_note = "credentials present" if settings.youtube_configured else "YOUTUBE_* credentials not set"
    return IntegrationsStatus(
        claude=IntegrationState(
            configured=settings.claude_configured,
            implemented=True,
            detail=f"model={settings.claude_model}" if settings.claude_configured else "ANTHROPIC_API_KEY not set",
        ),
        ffmpeg=IntegrationState(
            configured=ffmpeg_version is not None,
            implemented=True,
            detail=ffmpeg_version or "ffmpeg/ffprobe not found on PATH",
        ),
        youtube_data_api=IntegrationState(
            configured=settings.youtube_configured,
            implemented=False,
            detail=f"{youtube_note}; upload planned for roadmap Phase 5",
        ),
        youtube_analytics_api=IntegrationState(
            configured=settings.youtube_configured,
            implemented=False,
            detail=f"{youtube_note}; collection planned for roadmap Phase 6",
        ),
        publishing_enabled=settings.youtube_publishing_enabled,
    )


@router.get("/integrations", response_model=IntegrationsStatus)
def get_integrations(settings: SettingsDep, ffmpeg: FFmpegDep) -> IntegrationsStatus:
    return integrations_status(settings, ffmpeg)
