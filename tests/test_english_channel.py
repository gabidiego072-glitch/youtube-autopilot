"""The English channel: its own narrators, planned topics, prompts, on-screen texts and daily check."""

import importlib.util
import json
from pathlib import Path

from app.models import Channel
from app.models.enums import RunStatus, VideoFormat
from app.services.autopilot.runner import create_run
from app.services.experiments import VOICES, choose, dimensions
from app.services.language import title_guide
from app.services.scripts.prompts import build_script_prompt
from app.services.styles import next_planned_topic, pov_script_note


def test_each_language_has_its_own_narrators():
    en = dimensions("en")["voice"]
    assert en and all(VOICES[v].language == "en" for v in en)
    assert all(VOICES[v].language == "es" for v in dimensions("es")["voice"])
    import random

    assert choose([], random.Random(1), dimensions("en"))["voice"] in en


def test_planned_topics_are_used_only_by_their_language(tmp_path, monkeypatch):
    from app.services import styles

    planned = tmp_path / "planned.json"
    planned.write_text(
        json.dumps(
            [
                {"premise": "¿Qué pasaría si todos fueran zombis menos tú?"},
                {"premise": "What if everyone became a zombie except you?", "language": "en"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(styles, "PLANNED_TOPICS", planned)
    assert next_planned_topic(set(), "es")["premise"].startswith("¿Qué")
    assert next_planned_topic(set(), "en")["premise"].startswith("What if")
    assert next_planned_topic({"What if everyone became a zombie except you?"}, "en") is None


def test_english_prompts_ask_for_what_if_titles_and_english_counters():
    prompt = build_script_prompt(
        video_format=VideoFormat.SHORT,
        topic="t",
        working_title="What if the Moon vanished?",
        target_duration_seconds=45,
        language="en",
        niche=None,
        style_guide=None,
        notes=None,
    )
    assert "What if" in title_guide("en") and title_guide("en") in prompt
    assert "DAY 1" in pov_script_note("en") and "DÍA" not in pov_script_note("en")
    assert "DÍA 1" in pov_script_note("es")


def test_billboard_texts_follow_the_video_language():
    from render_engines.cinematic import texts

    try:
        texts.LANG = "en"
        assert texts.tr("breaking_1") == "BREAKING NEWS"
        texts.LANG = "es"
        assert texts.tr("breaking_1") == "ÚLTIMA HORA"
    finally:
        texts.LANG = "es"


def test_daily_check_is_per_channel(db):
    spec = importlib.util.spec_from_file_location(
        "autopilot_cli", Path(__file__).parent.parent / "scripts" / "autopilot.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    spanish = Channel(name="Qué Pasaría Si", language="es")
    english = Channel(name="What If (Around the World)", language="en")
    db.add_all([spanish, english])
    db.commit()
    run = create_run(db, spanish)
    run.status = RunStatus.PUBLISHED
    db.commit()
    assert cli.daily_done(db, spanish.id) == 0
    assert cli.daily_done(db, english.id) == 1  # the Spanish video does not count for the English channel
    assert cli.find_channel(db, "What If (Around the World)").language == "en"
