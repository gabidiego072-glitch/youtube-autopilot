"""What is working in the market: the most viewed recent Shorts of our format, in both languages.

Nov 16, from the owner: we only ever studied our own videos; we must also study what the Shorts market is
watching. This reads YouTube's own data with the channel's read-only access (no extra key): the most viewed
Shorts of the last weeks for "what if" style searches, with views, length, likes, comments and channel, so the
ideas and the format can follow what people actually watch. Titles are studied, never copied.

Cost: each search is 100 units of the 10,000 daily YouTube quota; the video details are 1 unit per 50 videos.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
QUERIES = {
    "es": ("qué pasaría si", "que pasaria si shorts", "qué pasaría si la tierra", "y si de repente"),
    "en": ("what if", "what would happen if", "what if the earth", "what if shorts animation"),
}


def _seconds(iso: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def market_report(api, days: int = 30, per_query: int = 25) -> dict:
    """{"since", "videos": [...most viewed first], "summary"}; `api` is the publisher's GoogleAPI."""
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    found: dict[str, dict] = {}
    for language, queries in QUERIES.items():
        for query in queries:
            data = api.json(
                "GET",
                SEARCH_URL,
                params={
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "videoDuration": "short",  # under 4 minutes
                    "order": "viewCount",
                    "publishedAfter": since,
                    "relevanceLanguage": language,
                    "maxResults": per_query,
                },
            )
            for item in data.get("items", []):
                vid = (item.get("id") or {}).get("videoId")
                if vid and vid not in found:
                    found[vid] = {"id": vid, "query": query, "language": language}
    ids = list(found)
    for start in range(0, len(ids), 50):
        data = api.json(
            "GET",
            VIDEOS_URL,
            params={"part": "snippet,statistics,contentDetails", "id": ",".join(ids[start : start + 50])},
        )
        for item in data.get("items", []):
            stats, snippet = item.get("statistics", {}), item.get("snippet", {})
            found[item["id"]].update(
                title=snippet.get("title", ""),
                channel=snippet.get("channelTitle", ""),
                published=snippet.get("publishedAt", "")[:10],
                seconds=_seconds(item.get("contentDetails", {}).get("duration", "")),
                views=int(stats.get("viewCount", 0) or 0),
                likes=int(stats.get("likeCount", 0) or 0),
                comments=int(stats.get("commentCount", 0) or 0),
            )
    videos = sorted(
        (v for v in found.values() if v.get("seconds", 0) and v["seconds"] <= 180),
        key=lambda v: v.get("views", 0),
        reverse=True,
    )
    return {"since": since[:10], "videos": videos, "summary": summarize(videos)}


def summarize(videos: list[dict]) -> dict:
    """Length and engagement of the top videos against the rest, per language."""
    out = {}
    for language in ("es", "en"):
        rows = [v for v in videos if v["language"] == language]
        if not rows:
            continue
        top = rows[: max(1, len(rows) // 5)]

        def median(values):
            values = sorted(values)
            return values[len(values) // 2] if values else 0

        out[language] = {
            "videos": len(rows),
            "top_20pct_median_views": median([v["views"] for v in top]),
            "top_20pct_median_seconds": median([v["seconds"] for v in top]),
            "all_median_seconds": median([v["seconds"] for v in rows]),
            "top_channels": sorted({v["channel"] for v in top}),
        }
    return out
