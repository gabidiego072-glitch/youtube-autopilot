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
