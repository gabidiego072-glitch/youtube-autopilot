import uuid

from fastapi import APIRouter, status

from app.api.deps import DbSession, SettingsDep
from app.api.lookups import get_project_or_404
from app.models import AnalyticsSnapshot
from app.models.enums import AnalyticsSource
from app.schemas.analytics import AnalyticsSnapshotCreate, AnalyticsSnapshotRead, DerivedMetricsRead
from app.services.analytics.metrics import derive
from app.services.analytics.sync import sync_youtube_metrics
from app.services.youtube.analytics_api import YouTubeAnalyticsCollector

router = APIRouter(tags=["analytics"])


def _read(snapshot: AnalyticsSnapshot, duration: float) -> AnalyticsSnapshotRead:
    d = derive(snapshot, duration)
    out = AnalyticsSnapshotRead.model_validate(snapshot)
    out.derived = DerivedMetricsRead(
        engagement_rate=d.engagement_rate,
        retention_ratio=d.retention_ratio,
        subscribers_per_1k_views=d.subscribers_per_1k_views,
    )
    return out


@router.post(
    "/projects/{project_id}/analytics",
    response_model=AnalyticsSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def record_snapshot(project_id: uuid.UUID, payload: AnalyticsSnapshotCreate, db: DbSession) -> AnalyticsSnapshotRead:
    """Record metrics manually (e.g. copied from YouTube Studio) until the collector exists."""
    project = get_project_or_404(db, project_id)
    data = payload.model_dump(exclude_none=True)
    snapshot = AnalyticsSnapshot(project_id=project.id, source=AnalyticsSource.MANUAL, **data)
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return _read(snapshot, project.target_duration_seconds)


@router.get("/projects/{project_id}/analytics", response_model=list[AnalyticsSnapshotRead])
def list_snapshots(project_id: uuid.UUID, db: DbSession) -> list[AnalyticsSnapshotRead]:
    project = get_project_or_404(db, project_id)
    return [_read(s, project.target_duration_seconds) for s in project.analytics_snapshots]


@router.post("/analytics/sync")
def sync_from_youtube(db: DbSession, settings: SettingsDep) -> dict:
    """Pull lifetime metrics of every published video from the YouTube Analytics API."""
    collector = YouTubeAnalyticsCollector(settings)
    collector.api  # noqa: B018 - fail fast (503) when the OAuth credentials are missing
    return sync_youtube_metrics(db, collector)
