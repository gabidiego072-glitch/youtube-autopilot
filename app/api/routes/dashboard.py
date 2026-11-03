from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import DbSession, FFmpegDep, SettingsDep
from app.api.routes.system import integrations_status
from app.models import Channel, Idea, Insight, RenderJob, VideoProject
from app.schemas.system import DashboardSummary
from app.services.reporting.builder import performances

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _counts(db, column) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).group_by(column)).all()
    return {str(k.value): n for k, n in rows if k is not None}


@router.get("/summary", response_model=DashboardSummary)
def summary(db: DbSession, settings: SettingsDep, ffmpeg: FFmpegDep) -> DashboardSummary:
    perf = performances(db)
    insights = db.scalars(select(Insight).order_by(Insight.created_at.desc()).limit(5))
    return DashboardSummary(
        channels=db.scalar(select(func.count()).select_from(Channel)) or 0,
        projects_by_status=_counts(db, VideoProject.status),
        projects_by_format=_counts(db, VideoProject.format),
        projects_by_category=_counts(db, VideoProject.category),
        ideas_by_status=_counts(db, Idea.status),
        render_jobs_by_status=_counts(db, RenderJob.status),
        videos_with_analytics=len(perf),
        total_views=sum(p.metrics.views for p in perf),
        latest_insights=[{"kind": i.kind, "title": i.title} for i in insights],
        integrations=integrations_status(settings, ffmpeg),
    )
