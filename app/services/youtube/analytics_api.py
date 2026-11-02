"""YouTube Analytics API collector. Not implemented yet (roadmap Phase 6)."""

from datetime import date

from app.core.config import Settings
from app.core.errors import IntegrationNotConfiguredError, IntegrationNotImplementedError
from app.services.youtube.base import VideoMetrics


class YouTubeAnalyticsCollector:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch_video_metrics(self, youtube_video_ids: list[str], start: date, end: date) -> list[VideoMetrics]:
        if not self._settings.youtube_configured:
            raise IntegrationNotConfiguredError(
                "YouTube is not configured. Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN."
            )
        raise IntegrationNotImplementedError(
            "YouTube Analytics collection is not implemented yet (roadmap Phase 6). "
            "Record metrics manually via POST /projects/{id}/analytics meanwhile."
        )
