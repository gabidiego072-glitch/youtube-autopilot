"""YouTube OAuth, resumable upload, analytics and trends against a mocked Google (no network, no real account).

These tests pin the HTTP protocol the code speaks. A real upload still has to be tried once with your own
credentials (python scripts/autopilot.py upload-test video.mp4), because only Google can confirm them.
"""

import json
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.core.errors import IntegrationNotConfiguredError, ProviderError, PublishingDisabledError
from app.models import AnalyticsSnapshot, Channel, VideoProject
from app.models.enums import AnalyticsSource, PrivacyStatus, VideoFormat
from app.services.analytics.sync import sync_youtube_metrics
from app.services.trends.signals import collect_signals, wikipedia_top
from app.services.youtube.analytics_api import YouTubeAnalyticsCollector
from app.services.youtube.base import UploadRequest
from app.services.youtube.data_api import CHUNK_UNIT, YouTubeDataAPIPublisher, clean_tags, video_body
from app.services.youtube.oauth import (
    TOKEN_URL,
    GoogleCredentials,
    build_auth_url,
    exchange_code,
    pkce_pair,
    scope_urls,
)
from tests.conftest import make_settings

CREDS = {
    "youtube_client_id": "client-id",
    "youtube_client_secret": "client-secret",
    "youtube_refresh_token": "refresh-token",
}
SESSION = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=abc"


class FakeGoogle:
    """Token endpoint + resumable upload server that stores bytes and can fail on demand."""

    def __init__(self, size: int, *, fail_put_at: set[int] | None = None, thumbnail_status: int = 200):
        self.size = size
        self.received = bytearray()
        self.calls: list[tuple[str, str]] = []
        self.tokens_issued = 0
        self.session_body: dict | None = None
        self.fail_put_at = fail_put_at or set()
        self.put_count = 0
        self.thumbnail_status = thumbnail_status
        self.expire_next_token = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append((request.method, url.split("?")[0]))
        if url.startswith(TOKEN_URL):
            form = parse_qs(request.content.decode())
            assert form["grant_type"] == ["refresh_token"] and form["refresh_token"] == ["refresh-token"]
            self.tokens_issued += 1
            return httpx.Response(200, json={"access_token": f"token-{self.tokens_issued}", "expires_in": 3599})
        assert request.headers["Authorization"].startswith("Bearer token-")
        if self.expire_next_token:
            self.expire_next_token = False
            return httpx.Response(401, json={"error": {"code": 401, "message": "expired"}})
        if request.method == "POST" and "uploadType=resumable" in url:
            assert request.headers["X-Upload-Content-Length"] == str(self.size)
            self.session_body = json.loads(request.content)
            return httpx.Response(200, headers={"Location": SESSION})
        if request.method == "PUT" and url == SESSION:
            return self._put(request)
        if "thumbnails/set" in url:
            if self.thumbnail_status != 200:
                return httpx.Response(
                    self.thumbnail_status, json={"error": {"errors": [{"reason": "forbidden"}], "message": "no"}}
                )
            return httpx.Response(200, json={"items": [{}]})
        if url.startswith("https://www.googleapis.com/youtube/v3/commentThreads"):
            return httpx.Response(200, json={"id": "comment-1"})
        raise AssertionError(f"unexpected call {request.method} {url}")

    def _put(self, request: httpx.Request) -> httpx.Response:
        content_range = request.headers["Content-Range"]
        if content_range.startswith("bytes */"):  # status query
            if len(self.received) == self.size:
                return self._done()
            return httpx.Response(308, headers={"Range": f"bytes=0-{len(self.received) - 1}"} if self.received else {})
        self.put_count += 1
        if self.put_count in self.fail_put_at:
            # Keep half the chunk, like a connection that dropped mid-transfer, then fail.
            start = int(content_range.split(" ")[1].split("-")[0])
            assert start == len(self.received), "client resent from the wrong offset"
            self.received += request.content[: len(request.content) // 2]
            return httpx.Response(503)
        start, end = (int(x) for x in content_range.split(" ")[1].split("/")[0].split("-"))
        assert start == len(self.received), f"chunk starts at {start}, server has {len(self.received)}"
        self.received += request.content
        assert len(self.received) == end + 1
        if len(self.received) == self.size:
            return self._done()
        return httpx.Response(308, headers={"Range": f"bytes=0-{end}"})

    def _done(self) -> httpx.Response:
        privacy = self.session_body["status"]["privacyStatus"]
        return httpx.Response(
            200, json={"id": "vid123", "status": {"privacyStatus": privacy, "uploadStatus": "uploaded"}}
        )


def _video(tmp_path, size: int):
    path = tmp_path / "video.mp4"
    path.write_bytes(bytes(i % 251 for i in range(size)))
    return path


def _publisher(fake, **settings) -> YouTubeDataAPIPublisher:
    return YouTubeDataAPIPublisher(
        make_settings(youtube_publishing_enabled=True, **CREDS, **settings),
        http=httpx.Client(transport=httpx.MockTransport(fake)),
        sleep=lambda _: None,
        chunk_bytes=CHUNK_UNIT,
    )


def _request(path, **kw) -> UploadRequest:
    return UploadRequest(
        video_path=path,
        title="¿Qué pasaría si la Tierra dejara de girar? <test>",
        description="Ciencia > ficción",
        tags=["ciencia", "qué pasaría si", "ciencia", "física"],
        category_id="28",
        **kw,
    )


# --- OAuth --------------------------------------------------------------------------------------
def test_consent_url_asks_for_offline_access_with_pkce():
    verifier, challenge = pkce_pair()
    assert 43 <= len(verifier) <= 128 and challenge and "=" not in challenge
    url = build_auth_url("cid", "http://127.0.0.1:8765", scope_urls(["upload", "analytics"]), "st", challenge)
    query = parse_qs(urlparse(url).query)
    assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]
    assert query["code_challenge_method"] == ["S256"] and query["redirect_uri"] == ["http://127.0.0.1:8765"]
    assert "https://www.googleapis.com/auth/youtube.upload" in query["scope"][0]
    with pytest.raises(ValueError):
        scope_urls(["everything"])


def test_code_exchange_requires_a_refresh_token():
    def handler(request):
        return httpx.Response(200, json={"access_token": "a", "expires_in": 3600})

    with pytest.raises(ProviderError, match="no refresh token"):
        exchange_code(httpx.Client(transport=httpx.MockTransport(handler)), "c", "s", "code", "http://x", "v")


def test_expired_refresh_token_explains_the_7_day_testing_limit():
    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Token has been expired"})

    creds = GoogleCredentials("cid-x", "secret-x", "refresh-x")
    with pytest.raises(IntegrationNotConfiguredError, match="7 days"):
        creds.access_token(httpx.Client(transport=httpx.MockTransport(handler)))
    assert "secret-x" not in repr(creds) and "refresh-x" not in repr(creds) and "redacted" in repr(creds)


# --- safety switches ----------------------------------------------------------------------------
def test_nothing_is_sent_while_publishing_is_disabled(tmp_path):
    fake = FakeGoogle(10)
    publisher = YouTubeDataAPIPublisher(make_settings(**CREDS), http=httpx.Client(transport=httpx.MockTransport(fake)))
    with pytest.raises(PublishingDisabledError):
        publisher.upload(_request(_video(tmp_path, 10)))
    assert fake.calls == []


@pytest.mark.parametrize(
    "extra", [{"privacy": PrivacyStatus.PUBLIC}, {"publish_at": datetime(2026, 12, 1, 18, 0, tzinfo=UTC)}]
)
def test_public_or_scheduled_needs_explicit_authorisation(tmp_path, extra):
    fake = FakeGoogle(10)
    with pytest.raises(PublishingDisabledError, match="YOUTUBE_ALLOW_PUBLIC"):
        _publisher(fake).upload(_request(_video(tmp_path, 10), **extra))
    assert fake.calls == []


def test_scheduled_upload_is_private_until_publish_at():
    body = video_body(
        UploadRequest(video_path="x", title="t", description="d", publish_at=datetime(2026, 12, 1, 18, 0, tzinfo=UTC))
    )
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["publishAt"] == "2026-12-01T18:00:00.000Z"


# --- resumable upload ---------------------------------------------------------------------------
def test_resumable_upload_in_chunks_with_thumbnail(tmp_path):
    size = CHUNK_UNIT * 2 + 1234
    video = _video(tmp_path, size)
    thumb = tmp_path / "thumb.jpg"
    thumb.write_bytes(b"\xff\xd8jpeg")
    fake = FakeGoogle(size)
    result = _publisher(fake).upload(_request(video, thumbnail_path=thumb, comment="¿Y tú qué harías?"))

    assert result.youtube_video_id == "vid123" and result.privacy == "private"
    assert result.thumbnail_set and result.comment_id is None  # comments are off by default
    assert bytes(fake.received) == video.read_bytes() and fake.put_count == 3
    snippet, status = fake.session_body["snippet"], fake.session_body["status"]
    assert "<" not in snippet["title"] and ">" not in snippet["description"]
    assert snippet["tags"] == ["ciencia", "qué pasaría si", "física"] and snippet["categoryId"] == "28"
    assert status == {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": False,
        "embeddable": True,
        "license": "youtube",
    }
    assert fake.tokens_issued == 1  # one access token reused for every request


def test_interrupted_upload_resumes_from_the_byte_the_server_kept(tmp_path):
    size = CHUNK_UNIT * 3
    video = _video(tmp_path, size)
    fake = FakeGoogle(size, fail_put_at={2})
    result = _publisher(fake).upload(_request(video))
    assert result.youtube_video_id == "vid123"
    assert bytes(fake.received) == video.read_bytes()


def test_expired_access_token_is_refreshed_once(tmp_path):
    video = _video(tmp_path, 1000)
    fake = FakeGoogle(1000)
    fake.expire_next_token = True
    assert _publisher(fake).upload(_request(video)).youtube_video_id == "vid123"
    assert fake.tokens_issued == 2


def test_thumbnail_refusal_is_a_warning_not_a_failed_upload(tmp_path):
    thumb = tmp_path / "t.jpg"
    thumb.write_bytes(b"jpeg")
    fake = FakeGoogle(1000, thumbnail_status=403)
    result = _publisher(fake).upload(_request(_video(tmp_path, 1000), thumbnail_path=thumb))
    assert result.youtube_video_id == "vid123" and not result.thumbnail_set
    assert "youtube.com/verify" in result.warnings[0]


def test_comment_is_posted_only_when_enabled(tmp_path):
    fake = FakeGoogle(1000)
    result = _publisher(fake, youtube_post_comment=True).upload(_request(_video(tmp_path, 1000), comment="¿Tú qué?"))
    assert result.comment_id == "comment-1" and "pin it by hand" in result.warnings[0]


def test_quota_errors_are_explained(tmp_path):
    def handler(request):
        if str(request.url).startswith(TOKEN_URL):
            return httpx.Response(200, json={"access_token": "token-1", "expires_in": 3600})
        return httpx.Response(403, json={"error": {"errors": [{"reason": "quotaExceeded"}], "message": "quota"}})

    publisher = YouTubeDataAPIPublisher(
        make_settings(youtube_publishing_enabled=True, **CREDS),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ProviderError, match="quota exhausted"):
        publisher.upload(_request(_video(tmp_path, 100)))


def test_tags_fit_youtube_limit():
    tags = clean_tags([f"etiqueta número {i}" for i in range(60)])
    assert sum(len(t) + 2 for t in tags) + len(tags) - 1 <= 500


# --- analytics ----------------------------------------------------------------------------------
def _analytics_client(seen):
    def handler(request):
        if str(request.url).startswith(TOKEN_URL):
            return httpx.Response(200, json={"access_token": "token-1", "expires_in": 3600})
        seen.append(dict(request.url.params))
        headers = [
            "views",
            "estimatedMinutesWatched",
            "averageViewDuration",
            "averageViewPercentage",
            "likes",
            "comments",
            "shares",
            "subscribersGained",
        ]
        return httpx.Response(
            200,
            json={"columnHeaders": [{"name": h} for h in headers], "rows": [[1500, 620.5, 31, 74.2, 90, 12, 7, 15]]},
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_analytics_sync_feeds_the_learning_loop(db_session_factory):
    seen = []
    collector = YouTubeAnalyticsCollector(make_settings(**CREDS), http=_analytics_client(seen))
    with db_session_factory() as db:
        channel = Channel(name="c", niche="n", language="es")
        db.add(channel)
        db.flush()
        project = VideoProject(
            channel_id=channel.id,
            working_title="w",
            topic="t",
            format=VideoFormat.SHORT,
            target_duration_seconds=45,
            youtube_video_id="vid123",
            published_at=datetime(2026, 10, 1, tzinfo=UTC),
        )
        db.add(project)
        db.commit()
        result = sync_youtube_metrics(db, collector, today=date(2026, 11, 2))
        assert result == {"videos": 1, "synced": 1, "errors": []}
        snap = db.query(AnalyticsSnapshot).one()
        assert snap.source == AnalyticsSource.YOUTUBE_ANALYTICS and snap.views == 1500
        assert snap.average_view_percentage == 74.2 and snap.impressions is None
        assert snap.engaged_views is None  # not in the answer -> left empty, never guessed
    assert seen[0]["filters"] == "video==vid123" and seen[0]["startDate"] == "2026-10-01"
    assert seen[0]["ids"] == "channel==MINE" and "engagedViews" in seen[0]["metrics"]


def test_analytics_without_credentials_is_not_faked():
    with pytest.raises(IntegrationNotConfiguredError):
        YouTubeAnalyticsCollector(make_settings()).fetch_video_metrics([], date(2026, 1, 1), date(2026, 1, 2))


# --- trends -------------------------------------------------------------------------------------
def test_wikipedia_trends_skip_special_pages_and_sum_days():
    def handler(request):
        articles = [
            {"article": "Wikipedia:Portada", "views": 10**6},
            {"article": "Especial:Buscar", "views": 10**5},
            {"article": "Eclipse_solar", "views": 5000},
            {"article": "Volcán", "views": 3000},
        ]
        return httpx.Response(200, json={"items": [{"articles": articles}]})

    topics = wikipedia_top(httpx.Client(transport=httpx.MockTransport(handler)), "ua", days=2)
    assert topics == ["Eclipse solar", "Volcán"]


def test_trend_failures_never_block_and_never_leak_the_key():
    def handler(request):
        return httpx.Response(429 if "wikimedia" in str(request.url) else 403)

    settings = make_settings(youtube_api_key="secret-key-123")
    signals = collect_signals(settings, http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert signals.curiosity_topics == [] and signals.competitor_videos == []
    assert len(signals.notes) == 2 and not any("secret-key-123" in n for n in signals.notes)
    assert signals.prompt_text() == ""


def test_competitor_videos_reach_the_prompt():
    def handler(request):
        url = str(request.url)
        if "wikimedia" in url:
            return httpx.Response(404)
        if "/search" in url:
            return httpx.Response(200, json={"items": [{"id": {"videoId": "a"}}, {"id": {"videoId": "b"}}]})
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "snippet": {"title": "¿Qué pasaría si la Luna desapareciera?", "channelTitle": "X"},
                        "statistics": {"viewCount": "120000"},
                    },
                    {
                        "snippet": {"title": "¿Y si no hubiera gravedad?", "channelTitle": "Y"},
                        "statistics": {"viewCount": "90000"},
                    },
                ]
            },
        )

    signals = collect_signals(
        make_settings(youtube_api_key="k"), http=httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert [v["views"] for v in signals.competitor_videos] == [120000, 90000]
    assert "do NOT copy" in signals.prompt_text() and "120,000 views" in signals.prompt_text()


def test_learning_score_rewards_viewers_who_stay(db_session_factory):
    from app.services.experiments import _scores

    with db_session_factory() as db:
        channel = Channel(name="c", niche="n", language="es")
        db.add(channel)
        db.flush()
        for vid, engaged in (("a", 900), ("b", 300)):
            project = VideoProject(
                channel_id=channel.id,
                working_title=vid,
                topic="t",
                format=VideoFormat.SHORT,
                target_duration_seconds=40,
                youtube_video_id=vid,
                features={"voice": vid},
            )
            db.add(project)
            db.flush()
            db.add(
                AnalyticsSnapshot(
                    project_id=project.id,
                    source=AnalyticsSource.YOUTUBE_ANALYTICS,
                    views=1000,
                    engaged_views=engaged,
                    average_view_duration_seconds=20,
                )
            )
        db.commit()
        scores = {features["voice"]: score for features, score in _scores(db, channel.id)}
    assert scores["a"] > scores["b"]
