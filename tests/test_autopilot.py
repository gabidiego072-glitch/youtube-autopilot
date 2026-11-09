"""The autonomous pipeline end to end, with stub AI/voice/Blender and real FFmpeg (edit, QA, thumbnails)."""

import copy
from pathlib import Path

import pytest

from app.models import Channel, PipelineRun
from app.models.enums import RunStatus, VideoFormat
from app.services.autopilot.runner import STEPS, Services, create_run, run_pipeline
from app.services.rendering.ffmpeg import FFmpeg
from tests.conftest import (
    FACTCHECK_PASS,
    IDEAS_RESPONSE,
    METADATA_RESPONSE,
    SCRIPT_RESPONSE,
    STORYBOARD_RESPONSE,
    StubAIProvider,
    make_settings,
)
from tests.test_content_pipeline import CONCEPTS, _wiki, _wiki_handler
from tests.test_media_pipeline import _StubBlender, _StubVoice

ffmpeg = FFmpeg()
pytestmark = pytest.mark.skipif(not ffmpeg.is_available(), reason="ffmpeg not installed")

FACTS = {"facts": []}
FULL_RUN = [IDEAS_RESPONSE, CONCEPTS, FACTS, SCRIPT_RESPONSE, FACTCHECK_PASS, STORYBOARD_RESPONSE, METADATA_RESPONSE]


def _services(tmp_path, responses, **settings) -> Services:
    return Services(
        ai=StubAIProvider(list(responses)),
        wiki=_wiki(_wiki_handler),
        tts=_StubVoice(),
        blender=_StubBlender(),
        ffmpeg=ffmpeg,
        settings=make_settings(media_root=tmp_path / "media", **settings),
        log=lambda *_: None,
    )


def _channel(db) -> Channel:
    channel = Channel(name="Qué Pasaría Si", niche="ciencia hipotética", language="es")
    db.add(channel)
    db.commit()
    return channel


def _status(run: PipelineRun) -> dict:
    return {s["name"]: s["status"] for s in run.steps}


def test_full_run_stops_for_approval_then_publishing_is_refused(db, tmp_path):
    channel = _channel(db)
    services = _services(tmp_path, FULL_RUN)
    run = run_pipeline(db, create_run(db, channel, VideoFormat.SHORT, "draft"), services)

    assert run.status == RunStatus.WAITING_APPROVAL, run.error
    statuses = _status(run)
    assert all(statuses[s] == "succeeded" for s in STEPS[: STEPS.index("approval")])
    assert statuses["approval"] == "blocked" and statuses["publish"] == "pending"
    details = {s["name"]: s.get("detail") for s in run.steps}
    assert details["topic"]["idea"].startswith("¿Qué pasaría si")
    assert Path(details["render"]["output"]).is_file() and details["render"]["resolution"] == "540x960"
    assert details["qa"]["passed"] is True
    assert Path(details["thumbnail"]["landscape"]).is_file() and Path(details["thumbnail"]["vertical"]).is_file()
    assert set(run.usage["by_step"]) >= {"topic", "research", "script", "fact_check", "storyboard", "metadata"}

    # A person approves the video, then the run resumes: publishing is still switched off, so it stops safely.
    from app.models import VideoProject
    from app.services.autopilot.runner import approve_run

    approve_run(db, run)
    run = run_pipeline(db, run, services)
    assert _status(run)["approval"] == "succeeded"
    assert run.status == RunStatus.FAILED and "Publishing is disabled" in run.error
    assert db.get(VideoProject, run.project_id).youtube_video_id is None


def test_run_without_credentials_never_fakes_an_upload(db, tmp_path):
    channel = _channel(db)
    services = _services(tmp_path, FULL_RUN, youtube_publishing_enabled=True)
    run = run_pipeline(db, create_run(db, channel, VideoFormat.SHORT, "draft", auto_publish=True), services)
    assert _status(run)["approval"] == "succeeded"  # authorised in advance by auto_publish + the switch
    assert run.status == RunStatus.FAILED and "YouTube is not configured" in run.error


def test_failed_fact_check_is_rewritten_once_then_the_next_idea_is_tried(db, tmp_path):
    from app.models import Idea, VideoProject
    from app.models.enums import IdeaStatus, ProjectStatus

    failing = copy.deepcopy(FACTCHECK_PASS)
    failing["verdicts"][0]["verdict"] = "incorrect"
    first_topic = [IDEAS_RESPONSE, CONCEPTS, FACTS, SCRIPT_RESPONSE, failing, SCRIPT_RESPONSE, failing]
    second_topic = [
        IDEAS_RESPONSE,
        CONCEPTS,
        FACTS,
        SCRIPT_RESPONSE,
        FACTCHECK_PASS,
        STORYBOARD_RESPONSE,
        METADATA_RESPONSE,
    ]
    run = run_pipeline(db, create_run(db, _channel(db)), _services(tmp_path, first_topic + second_topic))
    assert run.status == RunStatus.WAITING_APPROVAL, run.error  # no human needed: it moved on by itself

    projects = db.query(VideoProject).order_by(VideoProject.created_at).all()
    rejected, used = projects
    assert rejected.status == ProjectStatus.ARCHIVED and "Rejected automatically" in rejected.notes
    assert len(rejected.scripts) == 2  # original + one rewrite with the corrections
    assert db.get(Idea, rejected.idea_id).status == IdeaStatus.REJECTED
    assert run.project_id == used.id and used.idea_id != rejected.idea_id


def test_gives_up_after_three_rejected_topics(db, tmp_path, monkeypatch):
    import app.services.autopilot.runner as runner

    monkeypatch.setattr(runner, "MAX_TOPIC_RESTARTS", 1)
    failing = copy.deepcopy(FACTCHECK_PASS)
    failing["verdicts"][0]["verdict"] = "incorrect"
    topic = [CONCEPTS, FACTS, SCRIPT_RESPONSE, failing, SCRIPT_RESPONSE, failing]
    run = run_pipeline(
        db, create_run(db, _channel(db)), _services(tmp_path, [IDEAS_RESPONSE, *topic, IDEAS_RESPONSE, *topic])
    )
    assert run.status == RunStatus.FAILED and _status(run)["fact_check"] == "blocked"
    assert "after trying 2 topics" in run.error and "(incorrect)" in run.error


def test_runs_resume_from_the_failed_step(db, tmp_path):
    channel = _channel(db)
    # The storyboard is rejected (planet environment for a street scene) -> the run stops there.
    bad = copy.deepcopy(STORYBOARD_RESPONSE)
    bad["scenes"][0]["environment"] = {"type": "space"}
    services = _services(tmp_path, [IDEAS_RESPONSE, CONCEPTS, FACTS, SCRIPT_RESPONSE, FACTCHECK_PASS, bad, bad])
    run = run_pipeline(db, create_run(db, channel), services)
    assert run.status == RunStatus.FAILED and _status(run)["storyboard"] == "failed"
    assert "cannot show a 'street' scene" in run.error
    # Resume: earlier steps are not repeated (no new ideas or scripts are requested).
    services.ai = StubAIProvider([STORYBOARD_RESPONSE, METADATA_RESPONSE])
    run = run_pipeline(db, run, services)
    assert run.status == RunStatus.WAITING_APPROVAL, run.error
    assert next(s for s in run.steps if s["name"] == "script")["attempts"] == 1


def test_autopilot_api_reports_missing_credentials(client):
    channel = client.post("/api/v1/channels", json={"name": "C"}).json()
    assert client.get("/api/v1/autopilot/preflight").json()["ready"] is False
    response = client.post("/api/v1/autopilot/runs", json={"channel_id": channel["id"]})
    assert response.status_code == 503
    assert any("GEMINI_API_KEY" in p for p in response.json()["detail"]["problems"])


# --- parallel rendering ---------------------------------------------------------------------------
def test_scenes_rendered_in_parallel_shards_are_reused_by_the_edit(db, tmp_path):
    from app.services.production.short import render_scene_shard, shard_scenes

    assert shard_scenes(7, 0, 3) == [0, 3, 6] and shard_scenes(7, 2, 3) == [2, 5]
    services = _services(tmp_path, FULL_RUN[:-1])
    run = run_pipeline(db, create_run(db, _channel(db), VideoFormat.SHORT, "draft"), services, until="storyboard")
    work = tmp_path / "media" / "autopilot" / str(run.id)
    shard_blender = _StubBlender()

    class NoVoice:  # the voice step's recordings must be reused, never redone with another narrator
        name = "none"

        def synthesize(self, text, output_path):
            raise AssertionError("voice re-synthesized during the shard render")

    no_voice = NoVoice()
    for shard in range(2):  # in CI each shard is a separate job on its own machine
        render_scene_shard(
            work / "production.json",
            "draft",
            work,
            blender=shard_blender,
            ffmpeg=ffmpeg,
            tts=no_voice,
            shard=shard,
            shards=2,
            log=lambda *_: None,
        )
    scenes = len(SCRIPT_RESPONSE["scenes"])
    assert len(shard_blender.specs) == scenes

    final = _services(tmp_path, [METADATA_RESPONSE])  # the job that edits: nothing left to render
    run = run_pipeline(db, run, final)
    assert run.status == RunStatus.WAITING_APPROVAL, run.error
    assert final.blender.specs == []


# --- publishing -----------------------------------------------------------------------------------
CREDS = {"youtube_client_id": "a", "youtube_client_secret": "b", "youtube_refresh_token": "c"}


def _recording_publisher(settings):
    from app.services.youtube.base import UploadResult
    from app.services.youtube.data_api import YouTubeDataAPIPublisher

    class Recording(YouTubeDataAPIPublisher):
        requests = []

        def upload(self, request):
            self.check_ready()
            self.check_privacy(request)
            self.requests.append(request)
            return UploadResult("vid42", privacy=request.privacy.value, thumbnail_set=True)

    return Recording(settings)


def test_authorised_run_uploads_as_private(db, tmp_path):
    from app.models import PublishJob, VideoProject
    from app.models.enums import PrivacyStatus, PublishStatus

    services = _services(tmp_path, FULL_RUN, youtube_publishing_enabled=True, **CREDS)
    services.publisher = _recording_publisher(services.settings)
    run = run_pipeline(db, create_run(db, _channel(db), VideoFormat.SHORT, "draft", auto_publish=True), services)
    assert run.status == RunStatus.PUBLISHED, run.error
    (request,) = services.publisher.requests
    assert request.privacy == PrivacyStatus.PRIVATE and request.thumbnail_path.is_file()
    assert request.video_path.is_file() and request.title == METADATA_RESPONSE["title"]
    project = db.get(VideoProject, run.project_id)
    assert project.youtube_video_id == "vid42"
    job = db.query(PublishJob).one()
    assert job.status == PublishStatus.PUBLISHED and job.privacy == PrivacyStatus.PRIVATE


def test_public_default_without_authorisation_never_uploads(db, tmp_path):
    services = _services(tmp_path, FULL_RUN, youtube_publishing_enabled=True, youtube_default_privacy="public", **CREDS)
    services.publisher = _recording_publisher(services.settings)
    run = run_pipeline(db, create_run(db, _channel(db), VideoFormat.SHORT, "draft", auto_publish=True), services)
    assert run.status == RunStatus.FAILED and "YOUTUBE_ALLOW_PUBLIC" in run.error
    assert services.publisher.requests == []


# --- variety between videos -------------------------------------------------------------------------
def test_second_video_is_steered_away_from_the_first(db, tmp_path):
    from app.models import VideoProject

    channel = _channel(db)
    first = run_pipeline(db, create_run(db, channel, VideoFormat.SHORT, "draft"), _services(tmp_path, FULL_RUN))
    assert first.status == RunStatus.WAITING_APPROVAL, first.error
    first_project = db.get(VideoProject, first.project_id)

    services = _services(tmp_path, FULL_RUN)
    second = run_pipeline(db, create_run(db, channel, VideoFormat.SHORT, "draft"), services)
    assert second.status == RunStatus.WAITING_APPROVAL, second.error
    second_project = db.get(VideoProject, second.project_id)

    assert second_project.category != first_project.category  # a different kind of topic
    prompts = [c["prompt"] for c in services.ai.calls]
    script_prompt = next(p for p in prompts if "Recent videos on this channel" in p)
    assert first_project.scripts[-1].title_question in script_prompt
    assert any("Variety: the last videos used these places" in p for p in prompts)


def test_pick_idea_prefers_new_categories_and_unlike_titles():
    from types import SimpleNamespace as NS

    from app.models.enums import ContentCategory
    from app.services.variety import RecentVideos, pick_idea, too_similar

    cats = list(ContentCategory)
    ideas = [
        NS(premise="¿Qué pasaría si la Tierra dejara de girar de golpe?", category=cats[0]),
        NS(premise="¿Qué pasaría si dejaras de dormir?", category=cats[1]),
        NS(premise="¿Qué pasaría si el Sol se apagara?", category=cats[2]),
    ]
    recent = RecentVideos(titles=["¿Qué pasaría si la Tierra dejara de girar?"], categories=[cats[1].value])
    assert too_similar(ideas[0].premise, recent.titles)
    assert pick_idea(ideas, recent) is ideas[2]  # 0 repeats a title, 1 repeats the last category
    assert pick_idea(ideas[:1], recent) is ideas[0]  # never blocks a run


def test_music_changes_between_videos():
    from app.services.audio.synth import music_variant

    variants = {music_variant(seed) for seed in range(30)}
    assert len(variants) >= 20


# --- experiments: each video tries variants, results pick the next ones -------------------------------
def test_experiment_choice_explores_then_exploits():
    import random

    from app.services.experiments import DIMENSIONS, MIN_TRIES, choose

    rng = random.Random(1)
    assert set(choose([], rng)) == set(DIMENSIONS)
    # Every option tried MIN_TRIES times; 'tense' music clearly wins -> chosen most of the time.
    history = []
    for dim, options in DIMENSIONS.items():
        for option in options:
            for _ in range(MIN_TRIES):
                base = {d: o[0] for d, o in DIMENSIONS.items()}
                history.append(({**base, dim: option}, 0.9 if option == "tense" else 0.3))
    picks = [choose(history, random.Random(seed))["music"] for seed in range(200)]
    assert picks.count("tense") / len(picks) > 0.7  # exploit ~75 %, the rest explores


def test_run_records_variants_and_applies_them(db, tmp_path):
    import json

    from app.models import VideoProject
    from app.services.experiments import HOOKS, VOICES

    used_voices = []

    class NamedVoice(_StubVoice):
        def __init__(self, voice_id):
            self.voice_id = voice_id

        def synthesize(self, text, output_path):
            used_voices.append(self.voice_id)
            return super().synthesize(text, output_path)

    services = _services(tmp_path, FULL_RUN)
    services.voices = NamedVoice
    run = run_pipeline(db, create_run(db, _channel(db), VideoFormat.SHORT, "draft"), services)
    assert run.status == RunStatus.WAITING_APPROVAL, run.error
    project = db.get(VideoProject, run.project_id)
    features = project.features
    assert (
        set(features) == {"voice", "music", "length", "hook", "style", "city_style"} and features["style"] == "classic"
    )
    assert features["city_style"] in ("new_york", "paris", "tokyo", "london")
    assert project.target_duration_seconds == int(features["length"])
    assert used_voices and set(used_voices) == {features["voice"]}
    script_prompt = next(c["prompt"] for c in services.ai.calls if "Hook style for this video" in c["prompt"])
    assert HOOKS[features["hook"]] in script_prompt
    production = json.loads((tmp_path / "media" / "autopilot" / str(run.id) / "production.json").read_text())
    assert production["music_variant"] % 5 == ["wistful", "tense", "bright", "curious", "rising"].index(
        features["music"]
    )
    credit = VOICES[features["voice"]].credit
    if credit:
        assert credit in project.metadata_versions[-1].description


def test_missing_voice_falls_back_and_is_recorded(db, tmp_path):
    from app.models import VideoProject

    services = _services(tmp_path, FULL_RUN)
    services.voices = lambda voice_id: None  # not installed
    run = run_pipeline(db, create_run(db, _channel(db), VideoFormat.SHORT, "draft"), services)
    assert db.get(VideoProject, run.project_id).features["voice"] == "davefx"


def test_daily_done_lets_safety_retries_skip_when_todays_video_exists(db):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "autopilot_cli", Path(__file__).parent.parent / "scripts" / "autopilot.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    channel = _channel(db)
    assert cli.daily_done(db) == 1  # nothing today: make a video
    run = create_run(db, channel)
    run.status = RunStatus.FAILED
    db.commit()
    assert cli.daily_done(db) == 1  # a failed attempt does not count
    run.status = RunStatus.WAITING_APPROVAL
    db.commit()
    assert cli.daily_done(db) == 0


def test_planned_pov_topic_goes_first_and_every_scene_is_first_person(db, tmp_path, monkeypatch):
    import json

    from app.services import styles

    planned = tmp_path / "planned.json"
    planned.write_text(
        json.dumps(
            [
                {
                    "premise": "¿Qué pasaría si todos fueran zombis menos tú?",
                    "style": "pov",
                    "category": "human_body",
                    "city_style": "new_york",
                    "notes": "SETTING: New York City.",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(styles, "PLANNED_TOPICS", planned)
    services = _services(tmp_path, FULL_RUN[1:], planned_topics_enabled=True)  # no idea generation needed
    run = run_pipeline(db, create_run(db, _channel(db)), services, until="storyboard")
    assert run.status != RunStatus.FAILED, run.error
    from app.models import VideoProject

    project = db.get(VideoProject, run.project_id)
    assert project.working_title.startswith("¿Qué pasaría si todos fueran zombis")
    assert project.features["style"] == "pov"
    script_prompt = services.ai.calls[2]["prompt"]
    assert "first-person POV" in script_prompt and "DÍA 1" in script_prompt
    specs = project.scripts[-1].scene_specs
    assert all(spec["camera"]["pov"] for spec in specs)
    assert all(s["environment"].get("style") == "new_york" for s in specs if s["environment"]["type"] == "city")
    assert "SETTING: New York City." in services.ai.calls[-1]["prompt"]  # the storyboard knows the setting
    # Used once: the next run goes back to generated ideas.
    from app.services.styles import next_planned_topic

    assert next_planned_topic({project.working_title}) is None


def test_recipe_storyboard_writes_a_production_that_renders(db, tmp_path):
    """Recipes pick the place; the script's scene scales follow it, so the render accepts every scene
    (a calm opening room turned into the street must not be checked as an 'interior' scene)."""
    from app.services.production.short import load_production

    scenes = len(SCRIPT_RESPONSE["scenes"])
    picks = {
        "scenes": [{"recipe": "wake_up", "threat": "none", "time_of_day": "dawn", "look": "normal"}]
        + [{"recipe": "street_run", "threat": "zombies", "time_of_day": "day", "look": "normal"}] * (scenes - 2)
        + [{"recipe": "space", "threat": "none", "time_of_day": "day", "look": "normal"}]
    }
    responses = [IDEAS_RESPONSE, CONCEPTS, FACTS, SCRIPT_RESPONSE, FACTCHECK_PASS, picks]
    services = _services(tmp_path, responses, recipes_enabled=True, default_style="pov")
    run = run_pipeline(db, create_run(db, _channel(db)), services, until="storyboard")
    assert run.status != RunStatus.FAILED, run.error
    production = load_production(tmp_path / "media" / "autopilot" / str(run.id) / "production.json")
    assert production["scenes"][0]["recipe"] == "street_watch"
    assert production["scenes"][-1]["camera"]["pov"] is False  # no hands floating in space
