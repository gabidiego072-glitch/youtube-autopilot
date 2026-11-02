import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.api.deps import DbSession, SettingsDep
from app.api.lookups import get_project_or_404
from app.models.enums import JobStatus, ProjectStatus
from app.services.youtube.base import UploadRequest
from app.services.youtube.data_api import YouTubeDataAPIPublisher

router = APIRouter(tags=["publishing"])


@router.get("/publishing/status")
def publishing_status(settings: SettingsDep) -> dict:
    return {
        "publishing_enabled": settings.youtube_publishing_enabled,
        "youtube_configured": settings.youtube_configured,
        "upload_implemented": False,
    }


@router.post("/projects/{project_id}/publish")
def publish(project_id: uuid.UUID, db: DbSession, settings: SettingsDep) -> dict:
    """Upload an approved project to YouTube.

    Today this always ends in an error (disabled, not configured, or not
    implemented) - it never reports a fake upload.
    """
    project = get_project_or_404(db, project_id)
    if project.status != ProjectStatus.READY_TO_PUBLISH:
        raise HTTPException(status_code=409, detail="Project must be approved (ready_to_publish) first.")
    publisher = YouTubeDataAPIPublisher(settings)
    publisher.check_ready()

    render = next(j for j in reversed(project.render_jobs) if j.status == JobStatus.SUCCEEDED)
    metadata = project.metadata_versions[-1]
    result = publisher.upload(
        UploadRequest(
            video_path=Path(render.output_path or ""),
            title=metadata.title,
            description=metadata.description,
            tags=metadata.tags,
            category_id=metadata.category_id,
        )
    )
    return {"youtube_video_id": result.youtube_video_id}  # pragma: no cover - Phase 5
