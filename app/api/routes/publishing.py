import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.api.deps import DbSession, SettingsDep
from app.api.lookups import get_project_or_404
from app.db.base import utcnow
from app.models import PublishJob
from app.models.enums import AssetKind, JobStatus, PrivacyStatus, ProjectStatus, PublishStatus
from app.services.youtube.base import UploadRequest
from app.services.youtube.data_api import YouTubeDataAPIPublisher

router = APIRouter(tags=["publishing"])


@router.get("/publishing/status")
def publishing_status(settings: SettingsDep) -> dict:
    return {
        "publishing_enabled": settings.youtube_publishing_enabled,
        "public_allowed": settings.youtube_allow_public,
        "default_privacy": settings.youtube_default_privacy,
        "youtube_configured": settings.youtube_configured,
        "upload_implemented": True,
    }


@router.post("/projects/{project_id}/publish")
def publish(project_id: uuid.UUID, db: DbSession, settings: SettingsDep, privacy: PrivacyStatus | None = None) -> dict:
    """Upload an approved project to YouTube (resumable upload + thumbnail).

    Private by default. Public needs YOUTUBE_ALLOW_PUBLIC=true as well as YOUTUBE_PUBLISHING_ENABLED=true.
    """
    project = get_project_or_404(db, project_id)
    if project.status != ProjectStatus.READY_TO_PUBLISH:
        raise HTTPException(status_code=409, detail="Project must be approved (ready_to_publish) first.")
    publisher = YouTubeDataAPIPublisher(settings)
    publisher.check_ready()

    render = next(j for j in reversed(project.render_jobs) if j.status == JobStatus.SUCCEEDED)
    metadata = project.metadata_versions[-1]
    thumb = next(
        (Path(a.uri) for a in reversed(project.assets) if a.kind == AssetKind.THUMBNAIL and "1280x720" in a.uri), None
    )
    request = UploadRequest(
        video_path=Path(render.output_path or ""),
        title=metadata.title,
        description=metadata.description,
        tags=metadata.tags,
        category_id=metadata.category_id,
        privacy=privacy or PrivacyStatus(settings.youtube_default_privacy),
        thumbnail_path=thumb,
        comment=metadata.pinned_comment,
        language=project.language,
    )
    publisher.check_privacy(request)
    job = PublishJob(project_id=project.id, metadata_id=metadata.id, privacy=request.privacy)
    job.status = PublishStatus.UPLOADING
    db.add(job)
    db.commit()
    try:
        result = publisher.upload(request)
    except Exception as exc:
        job.status, job.error = PublishStatus.FAILED, getattr(exc, "message", str(exc))
        db.commit()
        raise
    job.status, job.youtube_video_id, job.error = (
        PublishStatus.PUBLISHED,
        result.youtube_video_id,
        "; ".join(result.warnings) or None,
    )
    project.youtube_video_id, project.status, project.published_at = (
        result.youtube_video_id,
        ProjectStatus.PUBLISHED,
        utcnow(),
    )
    db.commit()
    return {
        "youtube_video_id": result.youtube_video_id,
        "privacy": result.privacy,
        "thumbnail_set": result.thumbnail_set,
        "warnings": result.warnings,
    }
