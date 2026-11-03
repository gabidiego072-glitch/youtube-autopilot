"""Interfaces for YouTube Data API (publishing) and YouTube Analytics API."""

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from app.models.enums import PrivacyStatus


@dataclass(frozen=True)
class UploadRequest:
    video_path: Path
    title: str
    description: str
    tags: list[str] = field(default_factory=list)
    category_id: str | None = None
    privacy: PrivacyStatus = PrivacyStatus.PRIVATE
    publish_at: datetime | None = None
    thumbnail_path: Path | None = None
    made_for_kids: bool = False
    comment: str | None = None  # posted after the upload when YOUTUBE_POST_COMMENT=true


@dataclass(frozen=True)
class UploadResult:
    youtube_video_id: str
    privacy: str = "private"
    upload_status: str | None = None
    thumbnail_set: bool = False
    comment_id: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VideoMetrics:
    youtube_video_id: str
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


class VideoPublisher(Protocol):
    def upload(self, request: UploadRequest) -> UploadResult: ...


class AnalyticsCollector(Protocol):
    def fetch_video_metrics(self, youtube_video_ids: list[str], start: date, end: date) -> list[VideoMetrics]: ...
