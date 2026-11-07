"""Pull lifetime metrics of every published video from YouTube Analytics into analytics snapshots.

The learning loop (category weights, best premises) reads the latest snapshot per video, so a daily
sync is all it takes for new ideas to be steered by real results.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalyticsSnapshot, VideoProject
from app.models.enums import AnalyticsSource


def sync_youtube_metrics(db: Session, collector, today: date | None = None) -> dict:
    today = today or date.today()
    projects = list(db.scalars(select(VideoProject).where(VideoProject.youtube_video_id.is_not(None))))
    synced, errors = 0, []
    for project in projects:
        start = project.published_at.date() if project.published_at else today - timedelta(days=28)
        try:
            (metrics,) = collector.fetch_video_metrics([project.youtube_video_id], start, today)
        except Exception as exc:  # noqa: BLE001 - one failing video must not stop the others
            errors.append({"project_id": str(project.id), "error": getattr(exc, "message", str(exc))})
            continue
        db.add(
            AnalyticsSnapshot(
                project_id=project.id,
                source=AnalyticsSource.YOUTUBE_ANALYTICS,
                views=metrics.views,
                engaged_views=getattr(metrics, "engaged_views", None),
                impressions=metrics.impressions,
                impressions_ctr=metrics.impressions_ctr,
                estimated_minutes_watched=metrics.estimated_minutes_watched,
                average_view_duration_seconds=metrics.average_view_duration_seconds,
                average_view_percentage=metrics.average_view_percentage,
                likes=metrics.likes,
                comments=metrics.comments,
                shares=metrics.shares,
                subscribers_gained=metrics.subscribers_gained,
            )
        )
        synced += 1
    db.commit()
    return {"videos": len(projects), "synced": synced, "errors": errors}
