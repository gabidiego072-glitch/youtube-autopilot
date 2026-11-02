import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AnalyticsSource, ReportType
from app.schemas.common import ORMModel


class AnalyticsSnapshotCreate(BaseModel):
    captured_at: datetime | None = None
    views: int = Field(ge=0)
    impressions: int | None = Field(default=None, ge=0)
    impressions_ctr: float | None = Field(default=None, ge=0, le=1)
    estimated_minutes_watched: float | None = Field(default=None, ge=0)
    average_view_duration_seconds: float | None = Field(default=None, ge=0)
    average_view_percentage: float | None = Field(default=None, ge=0)
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    subscribers_gained: int = Field(default=0)


class DerivedMetricsRead(BaseModel):
    engagement_rate: float | None
    retention_ratio: float | None
    subscribers_per_1k_views: float | None


class AnalyticsSnapshotRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    captured_at: datetime
    source: AnalyticsSource
    views: int
    impressions: int | None
    impressions_ctr: float | None
    estimated_minutes_watched: float | None
    average_view_duration_seconds: float | None
    average_view_percentage: float | None
    likes: int
    comments: int
    shares: int
    subscribers_gained: int
    derived: DerivedMetricsRead | None = None


class InsightRead(ORMModel):
    id: uuid.UUID
    channel_id: uuid.UUID | None
    kind: str
    title: str
    detail: str
    evidence: dict
    created_at: datetime


class ReportCreate(BaseModel):
    report_type: ReportType = ReportType.CUSTOM
    period_start: datetime
    period_end: datetime
    channel_id: uuid.UUID | None = None


class ReportRead(ORMModel):
    id: uuid.UUID
    channel_id: uuid.UUID | None
    report_type: ReportType
    period_start: datetime
    period_end: datetime
    content: dict
    created_at: datetime
