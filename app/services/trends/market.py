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
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
QUERIES = {
    "es": (
        "qué pasaría si",
        "que pasaria si shorts",
        "qué pasaría si la tierra",
        "qué pasaría si los humanos",
        "y si de repente",
        "qué pasaría si el sol",
    ),
    "en": (
        "what if",
        "what would happen if",
        "what if the earth",
        "what if humans",
        "what if you",
        "what if the sun",
    ),
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
                channel_id=snippet.get("channelId", ""),
                tags=(snippet.get("tags") or [])[:12],
                description=(snippet.get("description") or "")[:200],
                views=int(stats.get("viewCount", 0) or 0),
                likes=int(stats.get("likeCount", 0) or 0),
                comments=int(stats.get("commentCount", 0) or 0),
            )
    channel_ids = sorted({v.get("channel_id") for v in found.values() if v.get("channel_id")})
    channels: dict[str, dict] = {}
    for start in range(0, len(channel_ids), 50):
        data = api.json(
            "GET", CHANNELS_URL, params={"part": "statistics,snippet", "id": ",".join(channel_ids[start : start + 50])}
        )
        for item in data.get("items", []):
            stats = item.get("statistics", {})
            channels[item["id"]] = {
                "subscribers": int(stats.get("subscriberCount", 0) or 0),
                "channel_videos": int(stats.get("videoCount", 0) or 0),
                "channel_created": (item.get("snippet", {}).get("publishedAt") or "")[:10],
            }
    for v in found.values():
        info = channels.get(v.get("channel_id", ""), {})
        v.update(info)
        # views per subscriber: a small channel with a big Short shows what the CONTENT does, not the channel size
        v["views_per_subscriber"] = round(v.get("views", 0) / max(1, info.get("subscribers", 0)), 2)
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
            # small channels (under 50k subscribers) whose Short got at least 5x their subscribers in views
            "outliers": [
                {k: v[k] for k in ("title", "channel", "views", "subscribers", "seconds", "views_per_subscriber")}
                for v in rows
                if v.get("subscribers", 0) < 50_000 and v.get("views_per_subscriber", 0) >= 5
            ][:15],
            "title_words": _common_words([v["title"] for v in top]),
        }
    return out


STOP = {
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "and",
    "is",
    "on",
    "for",
    "if",
    "what",
    "you",
    "your",
    "would",
    "with",
    "el",
    "la",
    "los",
    "las",
    "de",
    "del",
    "que",
    "qué",
    "si",
    "un",
    "una",
    "y",
    "en",
    "se",
    "por",
    "para",
    "es",
    "shorts",
    "short",
    "pasaría",
    "pasaria",
    "happen",
    "this",
    "it",
    "al",
    "lo",
    "tu",
    "te",
    "le",
}


def _common_words(titles: list[str], limit: int = 25) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for title in titles:
        for word in set(re.findall(r"[\wáéíóúñü]+", title.lower())):
            if len(word) > 2 and word not in STOP and not word.isdigit():
                counts[word] = counts.get(word, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
