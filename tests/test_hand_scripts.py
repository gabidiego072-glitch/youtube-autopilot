"""Scripts written by hand (by Claude) in planned_topics.json are used as they are (Nov 18)."""

import json
from types import SimpleNamespace

import pytest

from app.models.enums import VideoFormat
from app.services import styles
from app.services.autopilot import runner
from app.services.scenes.recipes import BUILDERS


def _topics(tmp_path, monkeypatch, topics):
    path = tmp_path / "planned.json"
    path.write_text(json.dumps(topics), encoding="utf-8")
    monkeypatch.setattr(styles, "PLANNED_TOPICS", path)


def test_every_queued_hand_script_is_valid_and_buildable():
    """The real queue: each hand script passes the script rules and every shot is a 3D scene the engine builds."""
    from app.services.scripts.generator import ScriptDraft, structure_problems

    for topic in styles.planned_topics():
        if not topic.get("script"):
            continue
        draft = ScriptDraft(**topic["script"], provider="claude", model="hand-written")
        lang = topic.get("language", "es")
        assert structure_problems(draft, VideoFormat.SHORT, lang) == [], topic["premise"]
        assert all(s.shot.get("recipe") in BUILDERS for s in draft.scenes), topic["premise"]


def test_the_hand_script_is_found_by_premise_and_language(tmp_path, monkeypatch):
    script = {"title_question": "¿Y si...?"}
    _topics(tmp_path, monkeypatch, [{"premise": "P", "language": "en", "script": script}, {"premise": "Q"}])
    assert styles.planned_script("P", "en") == script
    assert styles.planned_script("P", "es") is None and styles.planned_script("Q", "es") is None


def test_a_hand_script_is_used_without_asking_the_ai(tmp_path, monkeypatch):
    queued = [t for t in json.loads(styles.PLANNED_TOPICS.read_text(encoding="utf-8")) if t.get("script")]
    if not queued:
        pytest.skip("no hand script queued")
    _topics(tmp_path, monkeypatch, queued[:1])
    project = SimpleNamespace(
        working_title=queued[0]["premise"], language=queued[0].get("language", "es"), format=VideoFormat.SHORT
    )
    services = SimpleNamespace(settings=runner.get_settings() if hasattr(runner, "get_settings") else None)
    monkeypatch.setattr(runner, "get_format_spec", lambda fmt, settings: SimpleNamespace(format=VideoFormat.SHORT))
    draft = runner._hand_script(project, services)
    assert draft.provider == runner.HAND_PROVIDER and draft.scenes[0].shot["recipe"] in BUILDERS


def test_a_planned_topic_is_used_until_uploaded_or_tried_three_times():
    class DB:
        def __init__(self, rows):
            self.rows = rows

        def execute(self, _query):
            return SimpleNamespace(all=lambda: self.rows)

    rows = [("A", None), ("A", None), ("B", "vid"), ("C", None), ("C", None), ("C", None)]
    assert runner._planned_used(DB(rows), None) == {"B", "C"}


def test_a_judge_with_no_verdict_does_not_count_as_a_failed_scene():
    from app.services.scenes.check import check_scene

    ai = SimpleNamespace(generate_json=lambda **_: SimpleNamespace(data={"seen": "?"}))
    with pytest.raises(ValueError):
        check_scene(ai, "line", [])


def test_hand_scripts_only_makes_no_ai_video(monkeypatch):
    """Nov 22: with no hand script queued, the run stops before the AI writes anything."""
    from app.services.autopilot.runner import StepBlocked, step_topic

    channel = SimpleNamespace(id=1, language="en", niche="", style_guide="")

    class DB:
        def get(self, *_):
            return channel

        def scalars(self, *_):
            return []

        def execute(self, *_):
            return SimpleNamespace(all=lambda: [])

    monkeypatch.setattr(runner, "next_planned_topic", lambda *a, **k: None)
    services = SimpleNamespace(settings=SimpleNamespace(hand_scripts_only=True, planned_topics_enabled=True))
    with pytest.raises(StepBlocked):
        step_topic(DB(), SimpleNamespace(channel_id=1), services, None)
