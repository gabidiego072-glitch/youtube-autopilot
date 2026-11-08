"""YouTube Data API v3 publisher: resumable upload, thumbnail, optional comment, processing status.

Safety rules, checked before any network call:
1. YOUTUBE_PUBLISHING_ENABLED must be true (default false): otherwise nothing is uploaded.
2. OAuth credentials must exist.
3. PUBLIC or scheduled (publishAt) videos also need YOUTUBE_ALLOW_PUBLIC=true. Without it every
   upload is private, which is the right mode for test uploads.

Note: while the Google Cloud project has not passed YouTube's API compliance audit, YouTube
itself locks every API upload as private, whatever privacy is requested.

Quota (default 10,000 units/day per project): videos.insert 1 unit, but its own limit of about
100 uploads/day; thumbnails.set 50; commentThreads.insert 50; videos.list 1.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC
from pathlib import Path

import httpx

from app.core.config import Settings
from app.core.errors import IntegrationNotConfiguredError, ProviderError, PublishingDisabledError
from app.models.enums import PrivacyStatus
from app.services.youtube.base import UploadRequest, UploadResult
from app.services.youtube.oauth import GoogleAPI, credentials_from_settings, raise_for_google

logger = logging.getLogger(__name__)

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
THUMBNAIL_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
COMMENTS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"

CHUNK_UNIT = 256 * 1024  # resumable chunks must be multiples of 256 KiB
RETRY_STATUS = {500, 502, 503, 504}
MAX_RETRIES = 6
MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024
TITLE_MAX, DESCRIPTION_MAX_BYTES, TAGS_MAX_CHARS = 100, 5000, 500


def clean_text(text: str) -> str:
    """YouTube rejects '<' and '>' in titles and descriptions."""
    return text.replace("<", "‹").replace(">", "›").strip()


def clean_tags(tags: list[str]) -> list[str]:
    """Tags count towards a 500-character total (a tag with spaces counts its quotes too)."""
    out, used = [], 0
    for tag in tags:
        tag = clean_text(tag).replace(",", " ")
        if not tag or tag in out:
            continue
        cost = len(tag) + (2 if " " in tag else 0) + (1 if out else 0)
        if used + cost > TAGS_MAX_CHARS:
            break
        out.append(tag)
        used += cost
    return out


def video_body(request: UploadRequest, language: str | None = None) -> dict:
    language = language or request.language
    title = clean_text(request.title)[:TITLE_MAX]
    description = clean_text(request.description).encode()[:DESCRIPTION_MAX_BYTES].decode(errors="ignore")
    snippet = {
        "title": title,
        "description": description,
        "tags": clean_tags(request.tags),
        "defaultLanguage": language,
        "defaultAudioLanguage": language,
    }
    if request.category_id:
        snippet["categoryId"] = str(request.category_id)
    status = {
        "privacyStatus": request.privacy.value,
        "selfDeclaredMadeForKids": request.made_for_kids,
        "embeddable": True,
        "license": "youtube",
    }
    if request.publish_at is not None:
        # Scheduled videos must be uploaded as private; YouTube makes them public at publishAt.
        status["privacyStatus"] = PrivacyStatus.PRIVATE.value
        when = request.publish_at if request.publish_at.tzinfo else request.publish_at.replace(tzinfo=UTC)
        status["publishAt"] = when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {"snippet": snippet, "status": status}


class YouTubeDataAPIPublisher:
    def __init__(
        self,
        settings: Settings,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        chunk_bytes: int | None = None,
    ) -> None:
        self._settings = settings
        self._http = http
        self._sleep = sleep
        self._chunk_bytes = chunk_bytes
        self._api: GoogleAPI | None = None

    # --- guards ------------------------------------------------------------------------
    def check_ready(self) -> None:
        if not self._settings.youtube_publishing_enabled:
            raise PublishingDisabledError(
                "Publishing is disabled. Set YOUTUBE_PUBLISHING_ENABLED=true only when you are ready to upload."
            )
        if not self._settings.youtube_configured:
            raise IntegrationNotConfiguredError(
                "YouTube is not configured. Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN."
            )

    def check_privacy(self, request: UploadRequest) -> None:
        public = request.privacy == PrivacyStatus.PUBLIC or request.publish_at is not None
        if public and not self._settings.youtube_allow_public:
            raise PublishingDisabledError(
                "Public or scheduled publishing is not authorised. Upload as private, or set "
                "YOUTUBE_ALLOW_PUBLIC=true once you have approved public publishing."
            )

    @property
    def api(self) -> GoogleAPI:
        if self._api is None:
            self._api = GoogleAPI(credentials_from_settings(self._settings), self._http)
        return self._api

    # --- upload ------------------------------------------------------------------------
    def upload(self, request: UploadRequest) -> UploadResult:
        self.check_ready()
        self.check_privacy(request)
        path = Path(request.video_path)
        if not path.is_file() or path.stat().st_size == 0:
            raise ProviderError(f"Video file not found or empty: {path}")
        body = video_body(request)
        session = self._start_session(body, path.stat().st_size)
        video = self._send_file(session, path)
        video_id = video["id"]
        logger.info("uploaded %s as %s (%s)", path.name, video_id, video.get("status", {}).get("privacyStatus"))

        warnings: list[str] = []
        thumbnail_set = False
        if request.thumbnail_path is not None:
            try:
                self.set_thumbnail(video_id, Path(request.thumbnail_path))
                thumbnail_set = True
            except (ProviderError, IntegrationNotConfiguredError) as exc:
                warnings.append(f"thumbnail: {exc.message}")
        comment_id = None
        if request.comment and self._settings.youtube_post_comment:
            try:
                comment_id = self.post_comment(video_id, request.comment)
                warnings.append("comment posted; pin it by hand in YouTube Studio (the API cannot pin)")
            except (ProviderError, IntegrationNotConfiguredError) as exc:
                warnings.append(f"comment: {exc.message}")
        return UploadResult(
            youtube_video_id=video_id,
            privacy=video.get("status", {}).get("privacyStatus", body["status"]["privacyStatus"]),
            upload_status=video.get("status", {}).get("uploadStatus"),
            thumbnail_set=thumbnail_set,
            comment_id=comment_id,
            warnings=warnings,
        )

    def _start_session(self, body: dict, size: int) -> str:
        response = self._with_retries(
            lambda: self.api.request(
                "POST",
                UPLOAD_URL,
                params={"uploadType": "resumable", "part": "snippet,status"},
                json=body,
                headers={"X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/mp4"},
            )
        )
        if response.status_code != 200 or "location" not in response.headers:
            raise_for_google(response)
        return response.headers["location"]

    def _chunk_size(self) -> int:
        if self._chunk_bytes:
            return max(1, self._chunk_bytes // CHUNK_UNIT) * CHUNK_UNIT
        return max(1, self._settings.youtube_upload_chunk_mb * 1024 * 1024 // CHUNK_UNIT) * CHUNK_UNIT

    def _send_file(self, session: str, path: Path) -> dict:
        size, chunk = path.stat().st_size, self._chunk_size()
        offset, failures = 0, 0
        with path.open("rb") as handle:
            while True:
                handle.seek(offset)
                data = handle.read(chunk)
                end = offset + len(data) - 1
                try:
                    response = self.api.request(
                        "PUT",
                        session,
                        content=data,
                        headers={"Content-Length": str(len(data)), "Content-Range": f"bytes {offset}-{end}/{size}"},
                    )
                except httpx.TransportError as exc:
                    response, error = None, str(exc)
                else:
                    error = f"HTTP {response.status_code}"
                if response is not None and response.status_code in (200, 201):
                    return response.json()
                if response is not None and response.status_code == 308:
                    offset, failures = _next_offset(response), 0
                    continue
                if response is not None and response.status_code not in RETRY_STATUS:
                    raise_for_google(response)
                failures += 1
                if failures > MAX_RETRIES:
                    raise ProviderError(f"Upload failed after {MAX_RETRIES} retries ({error}).")
                self._sleep(min(64, 2**failures))
                queried = self._query_offset(session, size, offset)
                if queried is None:  # the server already has everything
                    return self._finish(session, size)
                offset = queried

    def _query_offset(self, session: str, size: int, last: int) -> int | None:
        """After an interruption, ask how many bytes the server kept (None = it has the whole file)."""
        try:
            response = self.api.request(
                "PUT", session, content=b"", headers={"Content-Length": "0", "Content-Range": f"bytes */{size}"}
            )
        except httpx.TransportError:
            return last  # still offline: retry from the last confirmed byte
        if response.status_code in (200, 201):
            return None
        if response.status_code == 308:
            return _next_offset(response)
        if response.status_code == 404:
            raise ProviderError("The upload session expired (sessions last about a week); start the upload again.")
        return last

    def _finish(self, session: str, size: int) -> dict:
        response = self.api.request(
            "PUT", session, content=b"", headers={"Content-Length": "0", "Content-Range": f"bytes */{size}"}
        )
        if response.status_code in (200, 201):
            return response.json()
        raise_for_google(response)
        return {}  # pragma: no cover

    def _with_retries(self, call: Callable[[], httpx.Response]) -> httpx.Response:
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = call()
            except httpx.TransportError as exc:
                if attempt == MAX_RETRIES:
                    raise ProviderError(f"YouTube is unreachable: {exc}") from exc
            else:
                if response.status_code not in RETRY_STATUS or attempt == MAX_RETRIES:
                    return response
            self._sleep(min(64, 2 ** (attempt + 1)))
        raise ProviderError("unreachable")  # pragma: no cover

    # --- other calls -------------------------------------------------------------------
    def set_thumbnail(self, video_id: str, image: Path) -> None:
        """Custom thumbnails need a phone-verified channel. JPEG/PNG up to 2 MB, 1280x720 recommended."""
        if not image.is_file():
            raise ProviderError(f"Thumbnail not found: {image}")
        data = image.read_bytes()
        if len(data) > MAX_THUMBNAIL_BYTES:
            raise ProviderError(f"Thumbnail is {len(data) // 1024} KB; YouTube accepts up to 2 MB.")
        mime = "image/png" if image.suffix.lower() == ".png" else "image/jpeg"
        response = self._with_retries(
            lambda: self.api.request(
                "POST", THUMBNAIL_URL, params={"videoId": video_id}, content=data, headers={"Content-Type": mime}
            )
        )
        if response.status_code >= 400:
            raise_for_google(response)

    def post_comment(self, video_id: str, text: str) -> str:
        """Top-level comment from the channel (needs the 'comments' scope). Pinning is not in the API."""
        body = {"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text[:10000]}}}}
        return self.api.json("POST", COMMENTS_URL, params={"part": "snippet"}, json=body)["id"]

    def video_status(self, video_id: str) -> dict:
        """Upload/processing state; shows whether YouTube locked the video private (audit) or rejected it."""
        data = self.api.json("GET", VIDEOS_URL, params={"part": "status,processingDetails", "id": video_id})
        if not data.get("items"):
            raise ProviderError(f"Video {video_id} not found on the channel.")
        item = data["items"][0]
        status = item.get("status", {})
        return {
            "upload_status": status.get("uploadStatus"),
            "privacy": status.get("privacyStatus"),
            "rejection_reason": status.get("rejectionReason"),
            "failure_reason": status.get("failureReason"),
            "processing": item.get("processingDetails", {}).get("processingStatus"),
        }

    def channel(self) -> dict:
        """The channel the refresh token belongs to (used to verify the credentials)."""
        data = self.api.json("GET", CHANNELS_URL, params={"part": "snippet,status", "mine": "true"})
        if not data.get("items"):
            raise IntegrationNotConfiguredError("This Google account has no YouTube channel.")
        item = data["items"][0]
        return {
            "id": item["id"],
            "title": item["snippet"]["title"],
            "long_uploads": item.get("status", {}).get("longUploadsStatus"),
        }


def _next_offset(response: httpx.Response) -> int:
    """308 Resume Incomplete: 'Range: bytes=0-N' means N+1 bytes were stored (no header = none)."""
    value = response.headers.get("range")
    if not value:
        return 0
    return int(value.rsplit("-", 1)[1]) + 1
