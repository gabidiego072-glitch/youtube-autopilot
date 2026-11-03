from fastapi import APIRouter

from app.api.deps import FFmpegDep, SettingsDep
from app.core.config import Settings
from app.schemas.system import IntegrationsStatus, IntegrationState
from app.services.rendering.blender import Blender
from app.services.rendering.ffmpeg import FFmpeg
from app.services.voice.piper import PiperTTS

router = APIRouter(prefix="/system", tags=["system"])


def integrations_status(settings: Settings, ffmpeg: FFmpeg) -> IntegrationsStatus:
    ffmpeg_version = ffmpeg.version()
    blender_version = Blender(settings.blender_binary).version()
    youtube_note = "credentials present" if settings.youtube_configured else "YOUTUBE_* credentials not set"
    return IntegrationsStatus(
        ai_provider=settings.ai_provider,
        gemini=IntegrationState(
            configured=settings.gemini_configured,
            implemented=True,
            detail=f"model={settings.gemini_model} (free tier)"
            if settings.gemini_configured
            else "GEMINI_API_KEY not set",
        ),
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
        blender=IntegrationState(
            configured=blender_version is not None,
            implemented=True,
            detail=(
                f"{blender_version}; renders every scene procedurally"
                if blender_version
                else "blender not found (scripts/install_blender.sh or BLENDER_BINARY)"
            ),
        ),
        voice=IntegrationState(
            configured=PiperTTS(settings.piper_binary, settings.piper_voice_model).is_available(),
            implemented=True,
            detail=f"piper {settings.piper_voice_model}" if settings.piper_voice_model else "PIPER_VOICE_MODEL not set",
        ),
        research=IntegrationState(
            configured=settings.research_enabled,
            implemented=True,
            detail=f"wikipedia ({settings.wikipedia_language}), free; reachability is checked per request",
        ),
        youtube_data_api=IntegrationState(
            configured=settings.youtube_configured,
            implemented=True,
            detail=f"{youtube_note}; resumable upload, private unless YOUTUBE_ALLOW_PUBLIC=true",
        ),
        youtube_analytics_api=IntegrationState(
            configured=settings.youtube_configured,
            implemented=True,
            detail=f"{youtube_note}; views, watch time, retention (impressions/CTR only via Studio)",
        ),
        publishing_enabled=settings.youtube_publishing_enabled,
    )


@router.get("/integrations", response_model=IntegrationsStatus)
def get_integrations(settings: SettingsDep, ffmpeg: FFmpegDep) -> IntegrationsStatus:
    return integrations_status(settings, ffmpeg)
