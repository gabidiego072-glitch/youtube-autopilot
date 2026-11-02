"""Builds period reports from data stored in the database."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AnalyticsSnapshot, Insight, VideoProject
from app.models.enums import ProjectStatus, VideoFormat
from app.services.analytics.metrics import derive
from app.services.learning.analyzer import VideoPerformance, summarize_by_format


def latest_snapshots(
    session: Session, channel_id: uuid.UUID | None = None
) -> list[tuple[VideoProject, AnalyticsSnapshot]]:
    latest = (
        select(AnalyticsSnapshot.project_id, func.max(AnalyticsSnapshot.captured_at).label("captured_at"))
        .group_by(AnalyticsSnapshot.project_id)
        .subquery()
    )
    stmt = (
        select(VideoProject, AnalyticsSnapshot)
        .join(AnalyticsSnapshot, AnalyticsSnapshot.project_id == VideoProject.id)
        .join(
            latest,
            (latest.c.project_id == AnalyticsSnapshot.project_id)
            & (latest.c.captured_at == AnalyticsSnapshot.captured_at),
        )
    )
    if channel_id is not None:
        stmt = stmt.where(VideoProject.channel_id == channel_id)
    return [(project, snapshot) for project, snapshot in session.execute(stmt)]


def performances(session: Session, channel_id: uuid.UUID | None = None) -> list[VideoPerformance]:
    return [
        VideoPerformance(
            project_id=str(project.id),
            title=project.working_title,
            format=project.format,
            metrics=derive(snapshot, project.target_duration_seconds),
        )
        for project, snapshot in latest_snapshots(session, channel_id)
    ]


def build_report(
    session: Session, *, period_start: datetime, period_end: datetime, channel_id: uuid.UUID | None = None
) -> dict:
    projects_stmt = select(VideoProject).where(
        VideoProject.created_at >= period_start, VideoProject.created_at < period_end
    )
    published_stmt = select(func.count()).where(
        VideoProject.published_at >= period_start, VideoProject.published_at < period_end
    )
    insights_stmt = select(Insight).where(Insight.created_at >= period_start, Insight.created_at < period_end)
    if channel_id is not None:
        projects_stmt = projects_stmt.where(VideoProject.channel_id == channel_id)
        published_stmt = published_stmt.where(VideoProject.channel_id == channel_id)
        insights_stmt = insights_stmt.where(Insight.channel_id == channel_id)

    created = list(session.scalars(projects_stmt))
    perf = performances(session, channel_id)
    top = sorted(perf, key=lambda p: p.metrics.views, reverse=True)[:5]

    return {
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "production": {
            "projects_created": len(created),
            "by_format": {fmt.value: sum(1 for p in created if p.format == fmt) for fmt in VideoFormat},
            "by_status": {s.value: n for s in ProjectStatus if (n := sum(1 for p in created if p.status == s))},
            "published": session.scalar(published_stmt) or 0,
        },
        "performance": {
            "videos_with_analytics": len(perf),
            "total_views": sum(p.metrics.views for p in perf),
            "by_format": summarize_by_format(perf),
            "top_videos": [{"project_id": p.project_id, "title": p.title, "views": p.metrics.views} for p in top],
        },
        "insights": [{"kind": i.kind, "title": i.title, "detail": i.detail} for i in session.scalars(insights_stmt)],
    }
