"""Video projects: the shared entry point for Shorts and long-form production."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, SettingsDep
from app.api.lookups import get_channel_or_404, get_project_or_404
from app.models import VideoProject
from app.models.enums import FactCheckStatus, JobStatus, ProjectStatus, VideoFormat
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.production.formats import DEFAULT_TARGET_DURATION, get_format_spec, validate_target_duration
from app.services.production.pipeline import transition

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: DbSession, settings: SettingsDep) -> VideoProject:
    channel = get_channel_or_404(db, payload.channel_id)
    duration = payload.target_duration_seconds or DEFAULT_TARGET_DURATION[payload.format]
    try:
        validate_target_duration(get_format_spec(payload.format, settings), duration)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    project = VideoProject(
        channel_id=channel.id,
        working_title=payload.working_title,
        topic=payload.topic,
        format=payload.format,
        category=payload.category,
        target_duration_seconds=duration,
        language=payload.language or channel.language,
        notes=payload.notes,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectRead])
def list_projects(
    db: DbSession,
    channel_id: uuid.UUID | None = None,
    format: VideoFormat | None = None,
    status: ProjectStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[VideoProject]:
    stmt = select(VideoProject).order_by(VideoProject.created_at.desc())
    if channel_id:
        stmt = stmt.where(VideoProject.channel_id == channel_id)
    if format:
        stmt = stmt.where(VideoProject.format == format)
    if status:
        stmt = stmt.where(VideoProject.status == status)
    return list(db.scalars(stmt.limit(min(limit, 500)).offset(offset)))


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: uuid.UUID, db: DbSession) -> VideoProject:
    return get_project_or_404(db, project_id)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(project_id: uuid.UUID, payload: ProjectUpdate, db: DbSession, settings: SettingsDep) -> VideoProject:
    project = get_project_or_404(db, project_id)
    changes = payload.model_dump(exclude_unset=True)
    if "target_duration_seconds" in changes:
        try:
            validate_target_duration(get_format_spec(project.format, settings), changes["target_duration_seconds"])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    for key, value in changes.items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/approve", response_model=ProjectRead)
def approve_for_publishing(project_id: uuid.UUID, db: DbSession) -> VideoProject:
    """Human sign-off. Requires a fact-checked script, metadata and a successful render."""
    project = get_project_or_404(db, project_id)
    if not project.scripts or project.scripts[-1].fact_check_status != FactCheckStatus.PASSED:
        raise HTTPException(status_code=409, detail="The latest script must pass the fact-check before approving.")
    if not project.metadata_versions:
        raise HTTPException(status_code=409, detail="Generate metadata before approving.")
    if not any(job.status == JobStatus.SUCCEEDED for job in project.render_jobs):
        raise HTTPException(status_code=409, detail="A successful render is required before approving.")
    transition(project, ProjectStatus.READY_TO_PUBLISH)
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/archive", response_model=ProjectRead)
def archive_project(project_id: uuid.UUID, db: DbSession) -> VideoProject:
    project = get_project_or_404(db, project_id)
    transition(project, ProjectStatus.ARCHIVED)
    db.commit()
    db.refresh(project)
    return project
