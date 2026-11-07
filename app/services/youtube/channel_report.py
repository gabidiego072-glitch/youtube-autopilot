"""Channel report from REAL YouTube data: every upload with its reach, retention, hook and traffic.

Used to understand why views go up or down. Nothing here is estimated or invented: each number comes
from the YouTube Data API (title, publish time, duration, public view count) or the YouTube Analytics
API (watch time, retention curve, engaged views, traffic sources). A metric YouTube does not return is
left out (null), never guessed.

- engaged_ratio = engagedViews / views: share of views that kept watching past the first seconds
  (the closest the API gets to Studio's "viewed vs swiped away").
- retention: audienceWatchRatio at points of the video (0.0 = start, 1.0 = end). For Shorts it can be
  above 1 because of loops. "hook" is the ratio at 10 % of the video: how many are still there.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime
from statistics import median
from zoneinfo import ZoneInfo

from app.core.errors import ProviderError
from app.services.youtube.oauth import GoogleAPI

DATA = "https://www.googleapis.com/youtube/v3"
REPORTS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
BASE_METRICS = (
    "views",
    "estimatedMinutesWatched",
    "averageViewDuration",
    "averageViewPercentage",
    "likes",
    "comments",
    "shares",
    "subscribersGained",
)
RETENTION_POINTS = (0.02, 0.1, 0.25, 0.5, 0.75, 1.0)
LOCAL = ZoneInfo("Europe/Madrid")
WEEKDAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def iso_seconds(duration: str) -> int:
    """'PT1M5S' -> 65."""
    match = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "")
    if not match:
        return 0
    d, h, m, s = (int(x or 0) for x in match.groups())
    return ((d * 24 + h) * 60 + m) * 60 + s


def _rows(data: dict) -> list[dict]:
    headers = [h["name"] for h in data.get("columnHeaders", [])]
    return [dict(zip(headers, row, strict=False)) for row in data.get("rows") or []]


class ChannelReport:
    def __init__(self, api: GoogleAPI) -> None:
        self.api = api
        self.notes: list[str] = []

    def report(self, start: date, end: date, retention_limit: int = 40) -> dict:
        videos = self.uploads()
        ids = [v["id"] for v in videos]
        totals = self.totals(ids, start, end)
        for video in videos:
            video.update(totals.get(video["id"], {}))
            views = video.get("views")
            engaged = video.get("engagedViews")
            video["engaged_ratio"] = round(engaged / views, 3) if views and engaged is not None else None
        for video in videos[:retention_limit]:
            video["retention"] = self.retention(video["id"], start, end)
            video["traffic"] = self.traffic(video["id"], start, end)
        return {
            "period": [start.isoformat(), end.isoformat()],
            "videos": videos,
            "by_publish_slot": by_publish_slot(videos),
            "daily_channel": self.daily(start, end),
            "notes": self.notes,
        }

    # --- Data API ---------------------------------------------------------------------------------
    def uploads(self) -> list[dict]:
        channel = self.api.json("GET", f"{DATA}/channels", params={"part": "contentDetails", "mine": "true"})
        items = channel.get("items") or []
        if not items:
            raise ProviderError("No YouTube channel for these credentials.")
        playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        ids, token = [], None
        while True:
            params = {"part": "contentDetails", "playlistId": playlist, "maxResults": 50}
            if token:
                params["pageToken"] = token
            page = self.api.json("GET", f"{DATA}/playlistItems", params=params)
            ids += [i["contentDetails"]["videoId"] for i in page.get("items", [])]
            token = page.get("nextPageToken")
            if not token:
                break
        videos = []
        for chunk in range(0, len(ids), 50):
            data = self.api.json(
                "GET",
                f"{DATA}/videos",
                params={"part": "snippet,contentDetails,status,statistics", "id": ",".join(ids[chunk : chunk + 50])},
            )
            for item in data.get("items", []):
                published = datetime.fromisoformat(item["snippet"]["publishedAt"].replace("Z", "+00:00"))
                local = published.astimezone(LOCAL)
                stats = item.get("statistics", {})
                videos.append(
                    {
                        "id": item["id"],
                        "title": item["snippet"]["title"],
                        "published_local": local.strftime("%Y-%m-%d %H:%M"),
                        "weekday": WEEKDAYS[local.weekday()],
                        "hour": local.hour,
                        "duration_s": iso_seconds(item["contentDetails"].get("duration", "")),
                        "privacy": item["status"].get("privacyStatus"),
                        "public_view_count": int(stats.get("viewCount", 0) or 0),
                    }
                )
        videos.sort(key=lambda v: v["published_local"], reverse=True)
        return videos

    # --- Analytics API ----------------------------------------------------------------------------
    def _report(self, **params) -> list[dict]:
        return _rows(self.api.json("GET", REPORTS_URL, params={"ids": "channel==MINE", **params}))

    def totals(self, ids: list[str], start: date, end: date) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for chunk in range(0, len(ids), 200):
            part = ids[chunk : chunk + 200]
            common = {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "dimensions": "video",
                "filters": "video==" + ",".join(part),
                "sort": "-views",
                "maxResults": 200,
            }
            try:
                rows = self._report(metrics=",".join((*BASE_METRICS, "engagedViews")), **common)
            except ProviderError as exc:
                self.notes.append(f"engagedViews not available, report without it: {exc}")
                rows = self._report(metrics=",".join(BASE_METRICS), **common)
            for row in rows:
                out[row.pop("video")] = row
        return out

    def retention(self, video_id: str, start: date, end: date) -> dict | None:
        try:
            rows = self._report(
                startDate=start.isoformat(),
                endDate=end.isoformat(),
                dimensions="elapsedVideoTimeRatio",
                metrics="audienceWatchRatio,relativeRetentionPerformance",
                filters=f"video=={video_id}",
            )
        except ProviderError as exc:
            self.notes.append(f"retention {video_id}: {exc}")
            return None
        if not rows:
            return None
        curve = sorted((float(r["elapsedVideoTimeRatio"]), r) for r in rows)

        def at(point: float) -> dict:
            return min(curve, key=lambda item: abs(item[0] - point))[1]

        return {
            "watch_ratio": {str(p): round(float(at(p)["audienceWatchRatio"]), 3) for p in RETENTION_POINTS},
            "relative": {
                str(p): round(float(at(p)["relativeRetentionPerformance"]), 3)
                for p in RETENTION_POINTS
                if at(p).get("relativeRetentionPerformance") is not None
            },
            "hook": round(float(at(0.1)["audienceWatchRatio"]), 3),
        }

    def traffic(self, video_id: str, start: date, end: date) -> dict | None:
        try:
            rows = self._report(
                startDate=start.isoformat(),
                endDate=end.isoformat(),
                dimensions="insightTrafficSourceType",
                metrics="views",
                filters=f"video=={video_id}",
            )
        except ProviderError as exc:
            self.notes.append(f"traffic {video_id}: {exc}")
            return None
        return {r["insightTrafficSourceType"]: int(r["views"]) for r in rows}

    def daily(self, start: date, end: date) -> list[dict]:
        try:
            return self._report(
                startDate=start.isoformat(),
                endDate=end.isoformat(),
                dimensions="day",
                metrics="views,engagedViews,subscribersGained,subscribersLost",
                sort="day",
            )
        except ProviderError:
            return self._report(
                startDate=start.isoformat(),
                endDate=end.isoformat(),
                dimensions="day",
                metrics="views,subscribersGained,subscribersLost",
                sort="day",
            )


def by_publish_slot(videos: list[dict]) -> dict:
    """Median views by publish hour and weekday (only public videos with analytics)."""
    hours, days = defaultdict(list), defaultdict(list)
    for video in videos:
        if video.get("privacy") != "public" or video.get("views") is None:
            continue
        hours[video["hour"]].append(video["views"])
        days[video["weekday"]].append(video["views"])
    return {
        "hour": {h: {"videos": len(v), "median_views": median(v)} for h, v in sorted(hours.items())},
        "weekday": {d: {"videos": len(v), "median_views": median(v)} for d, v in days.items()},
    }
