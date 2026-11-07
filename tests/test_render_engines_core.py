"""Pure-Python parts of the 3D engines (no Blender needed)."""

import json
import math
from pathlib import Path

import pytest

from render_engines.core.colors import hex_to_linear
from render_engines.core.noise import fbm, value_noise
from render_engines.core.spec import SpecError, build_context, load_spec, resolution, validate_spec
from render_engines.core.timeline import PositionTrack, Timeline

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "scenes"
CINEMATIC = EXAMPLES / "what_if_grow_each_step.json"


def test_example_specs_are_valid_and_on_theme():
    specs = sorted(EXAMPLES.glob("*.json"))  # top-level examples; urban/ holds engine test scenes
    assert specs
    for path in specs:
        spec = load_spec(path)
        assert spec["engine"] == "cinematic"
        assert 5 <= spec["duration_seconds"] <= 10
        assert spec["title"].startswith("¿Qué pasaría si")


def _minimal(**overrides) -> dict:
    spec = {"engine": "cinematic", "duration_seconds": 5, "camera": {"shots": [{"time": 0, "location": [0, -5, 2]}]}}
    return {**spec, **overrides}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"engine": "unreal"}, "engine"),
        ({"engine": "voxel"}, "engine"),  # the game-style engine was removed
        ({"environment": {"type": "underwater"}}, "environment"),
        ({"props": [{"id": "p", "type": "spaceship", "location": [0, 0, 0]}]}, "prop type"),
        ({"props": [{"id": "p", "type": "planet", "location": [0, 0]}]}, "location"),
        ({"actions": [{"type": "explode"}]}, "Unknown action"),
        ({"duration_seconds": 0}, "duration"),
        ({"fps": 23}, "fps"),
        ({"camera": {"shots": []}}, "shots"),
        ({"camera": {"shots": [{"time": 2, "location": [0, 0, 0]}, {"time": 1, "location": [0, 0, 0]}]}}, "ascending"),
        ({"characters": [{"id": "a"}, {"id": "a"}]}, "unique"),
        ({"actions": [{"type": "walk", "character": "ghost"}]}, "unknown id"),
        ({"actions": [{"type": "jump", "start": 99}]}, "outside"),
        ({"captions": [{"text": "hi", "start": 3, "end": 2}]}, "caption"),
    ],
)
def test_spec_validation_errors(overrides, message):
    with pytest.raises(SpecError, match=message):
        validate_spec(_minimal(**overrides))


def test_load_spec_reports_bad_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(SpecError):
        load_spec(bad)


def test_resolutions_support_both_aspects_with_even_dimensions():
    assert resolution("16:9", "final") == (1920, 1080)
    assert resolution("9:16", "final") == (1080, 1920)
    assert resolution("9:16", "draft") == (540, 960)
    for aspect in ("16:9", "9:16"):
        for scale in (0.07, 0.13, 0.333):
            w, h = resolution(aspect, "draft", scale)
            assert w % 2 == 0 and h % 2 == 0
    with pytest.raises(SpecError):
        resolution("4:3", "draft")


def test_context_frames():
    spec = json.loads(CINEMATIC.read_text())
    ctx = build_context(spec, "9:16", "draft")
    assert ctx.portrait and ctx.frame_count == 192 and ctx.frame_end == 192
    assert ctx.frame(1.0) == 25
    assert build_context(spec, "16:9", "test", max_frames=3).frame_count == 3


def test_noise_is_deterministic_and_bounded():
    assert value_noise(1.5, 2.5, 3) == value_noise(1.5, 2.5, 3)
    assert value_noise(1.5, 2.5, 3) != value_noise(1.5, 2.5, 4)
    samples = [fbm(x * 0.37, y * 0.29, 5) for x in range(30) for y in range(30)]
    assert all(0.0 <= s <= 1.0 for s in samples)


def test_colors_are_linearised():
    r, g, b, a = hex_to_linear("#808080")
    assert math.isclose(r, 0.2158, abs_tol=1e-3) and a == 1.0


def test_position_track_interpolates():
    track = PositionTrack((0, 0, 0))
    track.add(10, (0, 0, 0))
    track.add(20, (10, 0, 0))
    assert track.at(0) == (0, 0, 0)
    assert track.at(15) == (5, 0, 0)
    assert track.at(99) == (10, 0, 0)
    timeline = Timeline()
    timeline.register("bot", (1, 2, 0), focus_height=1.5)
    assert timeline.focus_point("bot", 5) == (1, 2, 1.5)


def test_focus_point_follows_scale():
    timeline = Timeline()
    timeline.register("giant", (0, 0, 0), focus_height=1.0, scale=1.0)
    timeline.scales["giant"].add(10, (1.0, 0, 0))
    timeline.scales["giant"].add(20, (5.0, 0, 0))
    assert timeline.focus_point("giant", 20)[2] == 5.0
    assert timeline.focus_point("giant", 15)[2] == 3.0


def test_narration_effects_and_places_are_in_the_catalog_and_validate():
    from render_engines.core.catalog import ACTIONS, ENVIRONMENTS, catalog_text
    from render_engines.core.spec import validate_spec

    for action in ("fire", "smoke", "crack", "flood", "collapse"):
        assert action in ACTIONS
    text = catalog_text()
    assert "kitchen" in text and "old_town" in text and "suburb" in text and "classroom" in text
    assert "interior" in ENVIRONMENTS
    spec = {
        "engine": "cinematic",
        "duration_seconds": 3,
        "fps": 24,
        "seed": 1,
        "environment": {"type": "interior", "room": "kitchen", "physics": True},
        "characters": [],
        "props": [],
        "actions": [
            {"type": "fire", "location": [-2.8, 0.6, 0.95], "start": 0.2, "end": 3, "size": 1},
            {"type": "crack", "location": [0, 2.69, 2.2], "surface": "wall", "start": 0.5, "end": 2},
            {"type": "flood", "start": 0, "end": 3, "height": 0.4},
        ],
        "camera": {"shots": [{"time": 0, "location": [0, -2, 1.6], "target": [0, 1, 1], "lens": 24}]},
        "captions": [],
    }
    assert validate_spec(spec) is spec


def test_storyboard_schema_lets_the_ai_choose_places_and_physics():
    from app.services.scenes.planner import SCENE_SCHEMA

    env = SCENE_SCHEMA["properties"]["environment"]["properties"]
    assert "physics" in env and "kitchen" in env["room"]["enum"] and "modern" in env["style"]["enum"]
    action = SCENE_SCHEMA["properties"]["actions"]["items"]["properties"]
    assert {"location", "surface", "size", "direction_deg", "accel"} <= set(action)
