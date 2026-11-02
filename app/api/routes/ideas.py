"""Idea generation and topic selection for 'What would happen if...?' videos."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AIProviderDep, DbSession, SettingsDep
from app.api.lookups import get_channel_or_404
from app.core.errors import NotFoundError
from app.models import Idea, VideoProject
from app.models.enums import IdeaStatus
from app.schemas.content import IdeaGenerateRequest, IdeaRead, IdeaSelectRequest
from app.schemas.project import ProjectRead
from app.services.ideas.generator import generate_ideas
from app.services.learning.feedback import category_weights, top_premises
from app.services.production.formats import DEFAULT_TARGET_DURATION, get_format_spec, validate_target_duration
from app.services.reporting.builder import performances

router = APIRouter(tags=["ideas"])


@router.post(
    "/channels/{channel_id}/ideas/generate", response_model=list[IdeaRead], status_code=status.HTTP_201_CREATED
)
def generate(channel_id: uuid.UUID, payload: IdeaGenerateRequest, db: DbSession, ai: AIProviderDep) -> list[Idea]:
    """Generate, de-duplicate and rank new premises, informed by past performance."""
    channel = get_channel_or_404(db, channel_id)
    existing = list(db.scalars(select(Idea.premise).where(Idea.channel_id == channel.id)))
    existing += list(db.scalars(select(VideoProject.working_title).where(VideoProject.channel_id == channel.id)))
    past = performances(db, channel.id)
    drafts = generate_ideas(
        ai,
        count=payload.count,
        language=channel.language,
        existing_premises=existing,
        category_weights=category_weights(past),
        top_premises=top_premises(past),
        focus=payload.focus or channel.niche,
    )
    ideas = [Idea(channel_id=channel.id, **draft.model_dump()) for draft in drafts]
    db.add_all(ideas)
    db.commit()
    return ideas


@router.get("/channels/{channel_id}/ideas", response_model=list[IdeaRead])
def list_ideas(
    channel_id: uuid.UUID, db: DbSession, status: IdeaStatus | None = IdeaStatus.NEW, limit: int = 50
) -> list[Idea]:
    get_channel_or_404(db, channel_id)
    stmt = select(Idea).where(Idea.channel_id == channel_id).order_by(Idea.score.desc()).limit(min(limit, 200))
    if status is not None:
        stmt = stmt.where(Idea.status == status)
    return list(db.scalars(stmt))


def _get_idea(db, idea_id: uuid.UUID) -> Idea:
    idea = db.get(Idea, idea_id)
    if idea is None:
        raise NotFoundError(f"Idea {idea_id} not found.")
    return idea


@router.post("/ideas/{idea_id}/select", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def select_idea(idea_id: uuid.UUID, payload: IdeaSelectRequest, db: DbSession, settings: SettingsDep) -> VideoProject:
    """Turn an idea into a video project (Short or long-form)."""
    idea = _get_idea(db, idea_id)
    if idea.status != IdeaStatus.NEW:
        raise HTTPException(status_code=409, detail=f"Idea is already '{idea.status.value}'.")
    duration = payload.target_duration_seconds or DEFAULT_TARGET_DURATION[payload.format]
    try:
        validate_target_duration(get_format_spec(payload.format, settings), duration)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    channel = get_channel_or_404(db, idea.channel_id)
    project = VideoProject(
        channel_id=channel.id,
        working_title=idea.premise[:200],
        topic=f"{idea.premise}\nAngle: {idea.angle}\nScience: {idea.science_basis}\nHook idea: {idea.hook}",
        format=payload.format,
        category=idea.category,
        idea_id=idea.id,
        target_duration_seconds=duration,
        language=channel.language,
    )
    db.add(project)
    db.flush()
    idea.status = IdeaStatus.USED
    idea.project_id = project.id
    db.commit()
    db.refresh(project)
    return project


@router.post("/ideas/{idea_id}/reject", response_model=IdeaRead)
def reject_idea(idea_id: uuid.UUID, db: DbSession) -> Idea:
    idea = _get_idea(db, idea_id)
    if idea.status == IdeaStatus.USED:
        raise HTTPException(status_code=409, detail="Idea is already used by a project.")
    idea.status = IdeaStatus.REJECTED
    db.commit()
    return idea
