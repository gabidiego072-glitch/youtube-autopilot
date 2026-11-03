"""Autonomous runs over the API: start, inspect and resume (after approval or a failure)."""

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, SessionFactoryDep, SettingsDep
from app.api.lookups import get_channel_or_404
from app.core.errors import NotFoundError
from app.models import PipelineRun
from app.models.enums import RunStatus, VideoFormat
from app.services.autopilot.factory import preflight, real_services
from app.services.autopilot.runner import create_run, run_pipeline

router = APIRouter(prefix="/autopilot", tags=["autopilot"])


class RunCreate(BaseModel):
    channel_id: uuid.UUID
    format: VideoFormat = VideoFormat.SHORT
    render_mode: str = Field(default="draft", pattern=r"^(preview|draft|hd|final)$")
    auto_publish: bool = False


class RunRead(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    project_id: uuid.UUID | None
    format: VideoFormat
    render_mode: str
    status: RunStatus
    current_step: str | None
    steps: list[dict]
    usage: dict
    auto_publish: bool
    error: str | None

    model_config = {"from_attributes": True}


def _execute(run_id: uuid.UUID, session_factory, settings) -> None:
    services = real_services(settings)
    with session_factory() as db:
        run_pipeline(db, db.get(PipelineRun, run_id), services)


@router.get("/preflight")
def check(settings: SettingsDep) -> dict:
    problems = preflight(settings)
    return {"ready": not problems, "problems": problems}


@router.post("/runs", response_model=RunRead, status_code=status.HTTP_202_ACCEPTED)
def start(
    payload: RunCreate,
    background: BackgroundTasks,
    db: DbSession,
    settings: SettingsDep,
    session_factory: SessionFactoryDep,
) -> PipelineRun:
    channel = get_channel_or_404(db, payload.channel_id)
    problems = preflight(settings)
    if problems:
        raise HTTPException(status_code=503, detail={"problems": problems})
    run = create_run(db, channel, payload.format, payload.render_mode, payload.auto_publish)
    background.add_task(_execute, run.id, session_factory, settings)
    return run


@router.get("/runs", response_model=list[RunRead])
def list_runs(db: DbSession, limit: int = 20) -> list[PipelineRun]:
    return list(db.scalars(select(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(min(limit, 100))))


@router.get("/runs/{run_id}", response_model=RunRead)
def get_run(run_id: uuid.UUID, db: DbSession) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise NotFoundError(f"Run {run_id} not found.")
    return run


@router.post("/runs/{run_id}/resume", response_model=RunRead, status_code=status.HTTP_202_ACCEPTED)
def resume(
    run_id: uuid.UUID,
    background: BackgroundTasks,
    db: DbSession,
    settings: SettingsDep,
    session_factory: SessionFactoryDep,
) -> PipelineRun:
    run = get_run(run_id, db)
    if run.status == RunStatus.RUNNING:
        raise HTTPException(status_code=409, detail="The run is already running.")
    background.add_task(_execute, run.id, session_factory, settings)
    return run
