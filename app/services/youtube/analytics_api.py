"""YouTube Analytics API v2 collector (free; needs the yt-analytics.readonly scope).

One report request per video (filters=video==ID) with views, watch time, retention and engagement.
Data appears with a delay of about 2-3 days. Impressions and click-through rate are NOT available in
the Analytics API (they come from the YouTube Reporting API's bulk "reach" reports), so they stay empty
unless recorded by hand from YouTube Studio.
"""

from __future__ import annotations

from datetime import date

import httpx

from app.core.config import Settings
from app.core.errors import ProviderError
from app.services.youtube.base import VideoMetrics
from app.services.youtube.oauth import GoogleAPI, credentials_from_settings

REPORTS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
METRICS = (
    "views",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "averageViewPercentage",
    "likes",
    "comments",
    "shares",
    "subscribersGained",
)


class YouTubeAnalyticsCollector:
    def __init__(self, settings: Settings, http: httpx.Client | None = None) -> None:
        self._settings = settings
        self._http = http
        self._api: GoogleAPI | None = None

    @property
    def api(self) -> GoogleAPI:
        if self._api is None:
            self._api = GoogleAPI(credentials_from_settings(self._settings), self._http)
        return self._api

    def fetch_video_metrics(self, youtube_video_ids: list[str], start: date, end: date) -> list[VideoMetrics]:
        if not youtube_video_ids:
            credentials_from_settings(self._settings)  # still tell the caller when credentials are missing
            return []
        return [self._video(video_id, start, end) for video_id in youtube_video_ids]

    def _video(self, video_id: str, start: date, end: date) -> VideoMetrics:
        params = {
            "ids": "channel==MINE",
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "metrics": ",".join((*METRICS, "engagedViews")),
            "filters": f"video=={video_id}",
        }
        try:
            data = self.api.json("GET", REPORTS_URL, params=params)
        except ProviderError:  # engagedViews not offered for this video/channel: ask without it
            data = self.api.json("GET", REPORTS_URL, params={**params, "metrics": ",".join(METRICS)})
        headers = [h["name"] for h in data.get("columnHeaders", [])]
        row = (data.get("rows") or [[0] * len(headers)])[0]
        values = dict(zip(headers, row, strict=False))
        return VideoMetrics(
            youtube_video_id=video_id,
            views=int(values.get("views", 0) or 0),
            impressions=None,
            impressions_ctr=None,
            estimated_minutes_watched=_float(values.get("estimatedMinutesWatched")),
            average_view_duration_seconds=_float(values.get("averageViewDuration")),
            average_view_percentage=_float(values.get("averageViewPercentage")),
            likes=int(values.get("likes", 0) or 0),
            comments=int(values.get("comments", 0) or 0),
            shares=int(values.get("shares", 0) or 0),
            subscribers_gained=int(values.get("subscribersGained", 0) or 0),
            engaged_views=None if values.get("engagedViews") is None else int(values["engagedViews"]),
        )


def _float(value) -> float | None:
    return None if value is None else float(value)
