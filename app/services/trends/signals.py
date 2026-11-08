"""Trend and competition signals for idea generation (best effort, free).

- Wikipedia pageviews (no key): the most-read articles of the last few days on es.wikipedia.
  Tells what people are curious about right now (eclipses, volcanoes, space missions...).
- YouTube search (YOUTUBE_API_KEY, optional): the most viewed recent «¿qué pasaría si...?» videos
  in Spanish. Used to find gaps and avoid copying; never to reuse titles.
  Cost: search.list counts against a separate limit of about 100 searches/day, videos.list 1 unit.

Any failure returns empty signals: trends improve ideas but never block a run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import httpx

from app.services.language import TRENDS, base

logger = logging.getLogger(__name__)

PAGEVIEWS_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{project}/all-access/{y}/{m:02d}/{d:02d}"
SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
SKIP_PREFIXES = (
    "Especial:",
    "Wikipedia:",
    "Archivo:",
    "Categoría:",
    "Anexo:",
    "Ayuda:",
    "Plantilla:",
    "Portal:",
    "Special:",
    "File:",
    "Category:",
    "Help:",
    "Template:",
    "Talk:",
    "Main_Page",
)
SKIP_TITLES = {"Wikipedia:Portada", "Main_Page", "-"}
DEFAULT_QUERIES = ("qué pasaría si", "qué pasaría si la tierra", "experimento mental ciencia")


@dataclass
class TrendSignals:
    curiosity_topics: list[str] = field(default_factory=list)  # Wikipedia, most read first
    audience: str = "Spanish-speaking"
    competitor_videos: list[dict] = field(default_factory=list)  # {"title", "views", "channel"}
    notes: list[str] = field(default_factory=list)  # what was skipped and why

    def prompt_text(self) -> str:
        parts = []
        if self.curiosity_topics:
            parts.append(
                f"What {self.audience} readers are curious about this week (most-read Wikipedia articles; use one "
                "only if it inspires a genuine, rigorous hypothetical with consequences for people):\n"
                + "\n".join(f"- {t}" for t in self.curiosity_topics)
            )
        if self.competitor_videos:
            parts.append(
                "Recent popular videos in this niche (do NOT copy them; find angles they missed):\n"
                + "\n".join(f"- {v['title']} ({v['views']:,} views)" for v in self.competitor_videos)
            )
        return "\n\n".join(parts)


def wikipedia_top(http: httpx.Client, user_agent: str, language: str = "es", days: int = 3, limit: int = 15) -> list:
    """Most-read articles over the last `days` complete days (summed)."""
    totals: dict[str, int] = {}
    today = datetime.now(UTC).date()
    last_error: Exception | None = None
    for back in range(1, days + 1):
        day: date = today - timedelta(days=back)
        url = PAGEVIEWS_URL.format(project=f"{language}.wikipedia", y=day.year, m=day.month, d=day.day)
        try:
            response = http.get(url, headers={"User-Agent": user_agent})
            if response.status_code == 404:  # that day is not published yet
                continue
            response.raise_for_status()
        except httpx.HTTPError as exc:  # rate limits: keep the days that did arrive
            last_error = exc
            continue
        for item in response.json()["items"][0]["articles"]:
            title = item["article"]
            if title in SKIP_TITLES or title.startswith(SKIP_PREFIXES):
                continue
            totals[title] = totals.get(title, 0) + int(item["views"])
    if not totals and last_error is not None:
        raise last_error
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return [title.replace("_", " ") for title, _ in ranked[:limit]]


def youtube_competitors(
    http: httpx.Client,
    api_key: str,
    *,
    queries: tuple[str, ...] = DEFAULT_QUERIES,
    region: str = "ES",
    language: str = "es",
    days: int = 30,
    limit: int = 15,
) -> list[dict]:
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids: list[str] = []
    for query in queries:
        response = http.get(
            SEARCH_URL,
            params={
                "part": "snippet",
                "q": query,
                "type": "video",
                "order": "viewCount",
                "publishedAfter": since,
                "relevanceLanguage": language,
                "regionCode": region,
                "maxResults": 15,
                "key": api_key,
            },
        )
        response.raise_for_status()
        ids += [i["id"]["videoId"] for i in response.json().get("items", []) if i["id"].get("videoId")]
    ids = list(dict.fromkeys(ids))[:50]
    if not ids:
        return []
    response = http.get(VIDEOS_URL, params={"part": "snippet,statistics", "id": ",".join(ids), "key": api_key})
    response.raise_for_status()
    videos = [
        {
            "title": item["snippet"]["title"],
            "channel": item["snippet"].get("channelTitle", ""),
            "views": int(item.get("statistics", {}).get("viewCount", 0)),
        }
        for item in response.json().get("items", [])
    ]
    return sorted(videos, key=lambda v: v["views"], reverse=True)[:limit]


def collect_signals(settings, http: httpx.Client | None = None) -> TrendSignals:
    http = http or httpx.Client(timeout=15.0)
    wiki_language, _, queries = TRENDS[base(settings.wikipedia_language)]
    signals = TrendSignals(audience="English-speaking" if wiki_language == "en" else "Spanish-speaking")
    try:
        signals.curiosity_topics = wikipedia_top(http, settings.wikipedia_user_agent, settings.wikipedia_language)
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
        signals.notes.append(f"wikipedia pageviews unavailable: {exc}")
    if settings.youtube_api_key_configured:
        try:
            signals.competitor_videos = youtube_competitors(
                http,
                settings.youtube_api_key.get_secret_value(),
                queries=queries,
                region=settings.youtube_region_code,
                language=wiki_language,
            )
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            # Never echo the request URL: it contains the API key.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            signals.notes.append(f"youtube search unavailable (HTTP {status})" if status else "youtube search failed")
    else:
        signals.notes.append("YOUTUBE_API_KEY not set: competitor research skipped")
    for note in signals.notes:
        logger.info("trends: %s", note)
    return signals
