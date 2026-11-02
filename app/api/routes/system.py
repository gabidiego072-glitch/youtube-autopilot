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
            detail=blender_version or "blender not found (scripts/install_blender.sh or BLENDER_BINARY)",
        ),
        ai_images=IntegrationState(
            configured=settings.image_provider_name is not None,
            implemented=True,
            detail=settings.image_provider_name
            or "not configured: set COMFYUI_URL + COMFYUI_IMAGE_WORKFLOW (self-hosted) or HF_TOKEN",
        ),
        ai_video=IntegrationState(
            configured=bool(settings.comfyui_url and settings.comfyui_video_workflow),
            implemented=True,
            detail="comfyui image-to-video workflow"
            if settings.comfyui_url and settings.comfyui_video_workflow
            else "not configured: stills are animated with free FFmpeg camera motion",
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
