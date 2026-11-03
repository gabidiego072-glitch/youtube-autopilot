import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession
from app.api.lookups import get_channel_or_404
from app.models import Insight
from app.schemas.analytics import InsightRead
from app.services.learning.analyzer import analyze
from app.services.reporting.builder import performances

router = APIRouter(prefix="/insights", tags=["insights"])


@router.post("/analyze", response_model=list[InsightRead])
def run_analysis(db: DbSession, channel_id: uuid.UUID | None = None) -> list[Insight]:
    """Analyze stored analytics and save the resulting insights."""
    if channel_id is not None:
        get_channel_or_404(db, channel_id)
    drafts = analyze(performances(db, channel_id))
    insights = [Insight(channel_id=channel_id, **vars(d)) for d in drafts]
    db.add_all(insights)
    db.commit()
    return insights


@router.get("", response_model=list[InsightRead])
def list_insights(db: DbSession, channel_id: uuid.UUID | None = None, limit: int = 50) -> list[Insight]:
    stmt = select(Insight).order_by(Insight.created_at.desc()).limit(min(limit, 500))
    if channel_id is not None:
        stmt = stmt.where(Insight.channel_id == channel_id)
    return list(db.scalars(stmt))
