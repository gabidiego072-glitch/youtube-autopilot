"""Personal stories like the reference videos: a companion with a name and their own voice, who appears when
they speak, texts on your phone, and the viewer's choice at the end (part 1)."""

from pathlib import Path

from app.services.autopilot.runner import companion_voice, is_companion_line
from app.services.editing.assembler import EditScene, plan_timeline, story_overlays, subtitle_cues
from app.services.scenes.recipe_planner import plan_with_recipes
from app.services.scenes.recipes import build, companion_palette
from tests.conftest import StubAIProvider

LUCIA = {"name": "Lucía", "gender": "female", "relation": "mejor amiga"}


def _pick(recipe, **extra):
    return {"recipe": recipe, "threat": "none", "time_of_day": "day", "look": "normal", **extra}


def test_the_companion_has_a_voice_of_their_own():
    assert companion_voice("es", "female", "kokoro_alex") == "kokoro_dora"
    assert companion_voice("en", "male", "kokoro_michael") == "kokoro_onyx"  # never the narrator's voice
    assert is_companion_line({"speaker": "Lucía"}, LUCIA)
    assert not is_companion_line({"speaker": "narrator"}, LUCIA) and not is_companion_line({}, LUCIA)


def test_the_companion_is_there_when_they_speak_and_looks_the_same():
    scenes = [
        {"narration": "Bajas a la calle y todo está en silencio.", "speaker": "narrator"},
        {"narration": "No abras la puerta.", "speaker": "Lucía"},
    ]
    ai = StubAIProvider([{"scenes": [_pick("street_watch"), _pick("room_view", room="living_room")]}])
    specs = plan_with_recipes(ai, scenes=scenes, durations=[3.0, 3.0], seed=2, city="madrid", companion=LUCIA)
    assert not any(c["id"] == "companion" for c in specs[0]["characters"])
    friend = next(c for c in specs[1]["characters"] if c["id"] == "companion")
    assert friend["palette"] == companion_palette("Lucía")
    assert "Lucía says:" in ai.calls[0]["prompt"]
    running = build("street_run", 4.0, seed=1, companion=LUCIA)  # she would be in your way: off-screen
    assert not any(c["id"] == "companion" for c in running["characters"])


def test_phone_texts_companion_words_and_the_final_choice_are_on_screen(tmp_path):
    slots = plan_timeline([3.0, 3.0], ["cut", "fade"], fps=24)
    scenes = [
        EditScene(Path("a.mp4"), Path("a.wav"), "Bajas a la calle", 2.5, slots[0], phone="no queda agua"),
        EditScene(Path("b.mp4"), Path("b.wav"), "No abras", 2.5, slots[1], companion=True),
    ]
    cues = subtitle_cues(scenes, 4)
    assert "<font" not in cues[0]["text"] and cues[-1]["text"].startswith("<font color")
    choice = {"question": "¿Qué harías?", "a": "Abrir", "b": "Esperar"}
    path = story_overlays(scenes, 1.6, "Lucía", choice, tmp_path / "s.ass", language="es")
    text = path.read_text(encoding="utf-8")
    assert "Lucía  ·  ahora" in text and "no queda agua" in text
    assert "¿QUÉ HARÍAS?" in text and "A  ·  Abrir" in text and "Comenta A o B" in text
    english = story_overlays(scenes, 0, "Zoe", choice, tmp_path / "e.ass", language="en").read_text()
    assert "Comment A or B" in english
    assert story_overlays(scenes[1:], 0, "", None, tmp_path / "n.ass") is None  # nothing to show


def test_videos_use_the_illustrated_look_and_lens():
    from app.services.scenes.recipe_planner import assemble

    specs = assemble([_pick("street_watch"), _pick("street_watch", look="xray")], [3.0, 3.0], seed=1, city="paris")
    assert specs[0]["look"] == specs[1]["look"] == "toon"  # the dark x-ray look left black screens (Nov 13)
    from app.services.editing.assembler import FISHEYE

    assert FISHEYE.startswith("lenscorrection=k1=-")  # barrel: lines bow outwards like the references


def test_the_story_happens_in_front_of_you():
    """'Lucía can't swallow either': across the table she puts a hand to her throat, the croissant on the plate."""
    from app.services.scenes.objects import library_model
    from render_engines.core.spec import validate_spec

    spec = build(
        "reaction", 4.0, seed=8, room="cafe", companion=LUCIA, gesture="throat", obj=library_model("croissant")
    )
    validate_spec(spec)
    lucia = next(c for c in spec["characters"] if c["id"] == "companion")
    assert lucia["palette"] == companion_palette("Lucía")
    assert any(a["type"] == "touch_throat" and a["character"] == "companion" for a in spec["actions"])
    croissant = next(p for p in spec["props"] if p["id"] == "obj")
    assert croissant["location"][2] > 0.7  # on the table, not on the floor
    assert sum(c["id"] == "companion" for c in spec["characters"]) == 1  # not added twice


def test_gestures_reach_the_person_in_front_of_you():
    spec = build("room_view", 4.0, seed=1, room="office", companion=LUCIA, gesture="cover")
    assert any(a["type"] == "cover" and a["character"] == "companion" for a in spec["actions"])
    nobody = build("space", 4.0, seed=1, gesture="wave")  # no one to do it: nothing breaks
    assert not any(a["type"] == "wave" for a in nobody["actions"])


def test_the_companion_must_really_talk():
    from app.models.enums import VideoFormat
    from app.services.scripts.generator import ScriptDraft, structure_problems
    from tests.conftest import SCRIPT_RESPONSE

    data = {**SCRIPT_RESPONSE, "scenes": [dict(s) for s in SCRIPT_RESPONSE["scenes"]]}
    data["visual_bible"] = {**data["visual_bible"], "companion": {"name": "Kenji", "gender": "male", "relation": "x"}}
    data["scenes"][1]["speaker"] = "Kenji"
    one = ScriptDraft(**data, provider="t", model="t")
    assert any("Kenji speaks 1 line" in p for p in structure_problems(one, VideoFormat.SHORT))  # Nov 13
    data["scenes"][2]["speaker"] = "kenji"
    two = ScriptDraft(**data, provider="t", model="t")
    assert not any("speaks" in p for p in structure_problems(two, VideoFormat.SHORT))
