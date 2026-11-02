import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession, SettingsDep
from app.api.lookups import get_project_or_404
from app.core.errors import NotFoundError
from app.models import RenderJob, Script
from app.models.enums import ProjectStatus
from app.schemas.render import RenderJobCreate, RenderJobRead
from app.services.production.formats import get_format_spec

router = APIRouter(tags=["rendering"])

RENDERABLE = {ProjectStatus.SCRIPT_READY, ProjectStatus.RENDERED, ProjectStatus.METADATA_READY}


@router.post("/projects/{project_id}/renders", response_model=RenderJobRead, status_code=status.HTTP_202_ACCEPTED)
def queue_render(project_id: uuid.UUID, payload: RenderJobCreate, db: DbSession, settings: SettingsDep) -> RenderJob:
    """Queue a render job.

    Jobs stay `queued` until the render worker exists (roadmap Phase 2).
    """
    project = get_project_or_404(db, project_id)
    if project.status not in RENDERABLE:
        raise HTTPException(status_code=409, detail=f"Project in '{project.status.value}' cannot be rendered.")
    if payload.script_id is not None:
        script = db.get(Script, payload.script_id)
        if script is None or script.project_id != project.id:
            raise NotFoundError("Script not found for this project.")
    else:
        if not project.scripts:
            raise HTTPException(status_code=409, detail="Project has no script.")
        script = project.scripts[-1]

    spec = get_format_spec(project.format, settings)
    job = RenderJob(project_id=project.id, script_id=script.id, width=spec.width, height=spec.height, fps=spec.fps)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("/projects/{project_id}/renders", response_model=list[RenderJobRead])
def list_renders(project_id: uuid.UUID, db: DbSession) -> list[RenderJob]:
    return get_project_or_404(db, project_id).render_jobs


@router.get("/renders/{job_id}", response_model=RenderJobRead)
def get_render(job_id: uuid.UUID, db: DbSession) -> RenderJob:
    job = db.get(RenderJob, job_id)
    if job is None:
        raise NotFoundError(f"Render job {job_id} not found.")
    return job
