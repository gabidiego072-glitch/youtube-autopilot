import uuid

from app.models import RenderJob
from app.models.enums import JobStatus
from tests.conftest import (
    FACTCHECK_PASS,
    LONG_SCRIPT_RESPONSE,
    METADATA_RESPONSE,
    SCRIPT_RESPONSE,
    StubAIProvider,
    make_settings,
)
from tests.helpers import create_project

PIPELINE = [SCRIPT_RESPONSE, METADATA_RESPONSE, FACTCHECK_PASS]  # call order


def test_render_requires_script(client, channel):
    project = create_project(client, channel["id"])
    assert client.post(f"/api/v1/projects/{project['id']}/renders", json={}).status_code == 409


def test_render_job_is_queued_with_format_dimensions(make_client, channel):
    client = make_client(ai=StubAIProvider([SCRIPT_RESPONSE, LONG_SCRIPT_RESPONSE]))
    short = create_project(client, channel["id"])
    long = create_project(client, channel["id"], format="long")
    for project in (short, long):
        client.post(f"/api/v1/projects/{project['id']}/scripts/generate")

    short_job = client.post(f"/api/v1/projects/{short['id']}/renders", json={}).json()
    long_job = client.post(f"/api/v1/projects/{long['id']}/renders", json={}).json()
    assert short_job["status"] == "queued"
    assert (short_job["width"], short_job["height"]) == (1080, 1920)
    assert (long_job["width"], long_job["height"]) == (1920, 1080)
    assert client.get(f"/api/v1/renders/{short_job['id']}").json()["id"] == short_job["id"]
    assert len(client.get(f"/api/v1/projects/{short['id']}/renders").json()) == 1


def _approved_project(client, db_session_factory, channel, **overrides) -> dict:
    project = create_project(client, channel["id"], **overrides)
    script = client.post(f"/api/v1/projects/{project['id']}/scripts/generate").json()
    job = client.post(f"/api/v1/projects/{project['id']}/renders", json={}).json()
    client.post(f"/api/v1/projects/{project['id']}/metadata/generate")
    with db_session_factory() as session:  # simulate a finished render
        render = session.get(RenderJob, uuid.UUID(job["id"]))
        render.status = JobStatus.SUCCEEDED
        render.output_path = "/tmp/video.mp4"
        session.commit()

    blocked = client.post(f"/api/v1/projects/{project['id']}/approve")
    assert blocked.status_code == 409 and "fact-check" in blocked.json()["detail"]
    client.post(f"/api/v1/projects/{project['id']}/scripts/{script['id']}/fact-check")
    approved = client.post(f"/api/v1/projects/{project['id']}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "ready_to_publish"
    return project


def test_approval_requires_finished_render(make_client, channel):
    client = make_client(ai=StubAIProvider([SCRIPT_RESPONSE, METADATA_RESPONSE, FACTCHECK_PASS]))
    project = create_project(client, channel["id"])
    script = client.post(f"/api/v1/projects/{project['id']}/scripts/generate").json()
    client.post(f"/api/v1/projects/{project['id']}/metadata/generate")
    client.post(f"/api/v1/projects/{project['id']}/scripts/{script['id']}/fact-check")
    response = client.post(f"/api/v1/projects/{project['id']}/approve")
    assert response.status_code == 409 and "render" in response.json()["detail"]


def test_publish_requires_approval(client, channel):
    project = create_project(client, channel["id"])
    assert client.post(f"/api/v1/projects/{project['id']}/publish").status_code == 409


def test_publish_is_disabled_by_default(make_client, db_session_factory, channel):
    client = make_client(ai=StubAIProvider(list(PIPELINE)))
    project = _approved_project(client, db_session_factory, channel)
    response = client.post(f"/api/v1/projects/{project['id']}/publish")
    assert response.status_code == 403
    assert response.json()["error"] == "publishing_disabled"


def test_publish_enabled_without_credentials(make_client, db_session_factory, channel):
    client = make_client(make_settings(youtube_publishing_enabled=True), ai=StubAIProvider(list(PIPELINE)))
    project = _approved_project(client, db_session_factory, channel)
    assert client.post(f"/api/v1/projects/{project['id']}/publish").status_code == 503


def test_public_upload_needs_its_own_authorisation(make_client, db_session_factory, channel):
    settings = make_settings(
        youtube_publishing_enabled=True, youtube_client_id="a", youtube_client_secret="b", youtube_refresh_token="c"
    )
    client = make_client(settings, ai=StubAIProvider(list(PIPELINE)))
    project = _approved_project(client, db_session_factory, channel)
    response = client.post(f"/api/v1/projects/{project['id']}/publish", params={"privacy": "public"})
    assert response.status_code == 403 and "YOUTUBE_ALLOW_PUBLIC" in response.json()["detail"]
    assert client.get(f"/api/v1/projects/{project['id']}").json()["status"] == "ready_to_publish"


def test_private_upload_records_the_video(make_client, db_session_factory, channel, monkeypatch):
    from app.services.youtube.base import UploadResult
    from app.services.youtube.data_api import YouTubeDataAPIPublisher

    sent = []

    def fake_upload(self, request):  # the HTTP protocol itself is covered in tests/test_youtube.py
        sent.append(request)
        return UploadResult("vid99", privacy=request.privacy.value)

    monkeypatch.setattr(YouTubeDataAPIPublisher, "upload", fake_upload)
    settings = make_settings(
        youtube_publishing_enabled=True, youtube_client_id="a", youtube_client_secret="b", youtube_refresh_token="c"
    )
    client = make_client(settings, ai=StubAIProvider(list(PIPELINE)))
    project = _approved_project(client, db_session_factory, channel)
    response = client.post(f"/api/v1/projects/{project['id']}/publish")
    assert response.status_code == 200 and response.json()["privacy"] == "private"
    assert sent[0].privacy.value == "private"
    body = client.get(f"/api/v1/projects/{project['id']}").json()
    assert body["status"] == "published" and body["youtube_video_id"] == "vid99"


def test_manual_upload_sends_the_project_language(make_client, db_session_factory, channel, monkeypatch):
    """An English video published by hand must reach YouTube as English, not the default Spanish."""
    from app.services.youtube.base import UploadResult
    from app.services.youtube.data_api import YouTubeDataAPIPublisher

    sent = []
    monkeypatch.setattr(
        YouTubeDataAPIPublisher, "upload", lambda self, request: sent.append(request) or UploadResult("v1", "private")
    )
    settings = make_settings(
        youtube_publishing_enabled=True, youtube_client_id="a", youtube_client_secret="b", youtube_refresh_token="c"
    )
    client = make_client(settings, ai=StubAIProvider(list(PIPELINE)))
    project = _approved_project(client, db_session_factory, channel, language="en")
    assert client.post(f"/api/v1/projects/{project['id']}/publish").status_code == 200
    assert sent[0].language == "en"
