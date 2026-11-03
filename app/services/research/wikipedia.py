"""Free research source: the public MediaWiki / Wikipedia REST APIs (no key needed).

Wikimedia requires a descriptive User-Agent with contact details
(WIKIPEDIA_USER_AGENT) and rate-limits aggressive clients.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import httpx


class ResearchUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class SourceSummary:
    title: str
    url: str
    extract: str
    source: str = "wikipedia"


class WikipediaClient:
    def __init__(
        self, language: str, user_agent: str, client: httpx.Client | None = None, timeout: float = 10.0
    ) -> None:
        self.language = language
        self._client = client or httpx.Client(timeout=timeout, headers={"User-Agent": user_agent})
        self._headers = {"User-Agent": user_agent}

    @property
    def _api(self) -> str:
        return f"https://{self.language}.wikipedia.org/w/api.php"

    def _get(self, url: str, params: dict | None = None) -> dict:
        try:
            response = self._client.get(url, params=params, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ResearchUnavailableError(f"Wikipedia request failed: {exc}") from exc
        if response.status_code == 404:
            return {}
        if response.status_code != 200:
            raise ResearchUnavailableError(f"Wikipedia returned HTTP {response.status_code}.")
        return response.json()

    def search(self, query: str, limit: int = 1) -> list[str]:
        data = self._get(
            self._api,
            {"action": "query", "list": "search", "srsearch": query, "srlimit": limit, "format": "json"},
        )
        return [hit["title"] for hit in data.get("query", {}).get("search", [])]

    def summary(self, title: str) -> SourceSummary | None:
        url = f"https://{self.language}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"
        data = self._get(url)
        extract = data.get("extract")
        if not extract or data.get("type") == "disambiguation":
            return None
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page", url)
        return SourceSummary(title=data.get("title", title), url=page_url, extract=extract)

    def lookup(self, query: str) -> SourceSummary | None:
        titles = self.search(query)
        return self.summary(titles[0]) if titles else None
