"""Pure-Python parts of the 3D engines (no Blender needed)."""

import json
import math
from pathlib import Path

import pytest

from render_engines.core.colors import hex_to_linear
from render_engines.core.noise import fbm, value_noise
from render_engines.core.spec import SpecError, build_context, load_spec, resolution, validate_spec
from render_engines.core.timeline import PositionTrack, Timeline
from render_engines.voxel.grid import VoxelGrid, block_hash
from render_engines.voxel.models import BOT_PALETTE, chest, explorer_bot
from render_engines.voxel.world import generate_world

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "scenes"
CINEMATIC = EXAMPLES / "cinematic_lantern_keeper.json"
VOXEL = EXAMPLES / "voxel_crystal_quest.json"


@pytest.mark.parametrize(("path", "engine"), [(CINEMATIC, "cinematic"), (VOXEL, "voxel")])
def test_example_specs_are_valid(path, engine):
    spec = load_spec(path)
    assert spec["engine"] == engine
    assert 5 <= spec["duration_seconds"] <= 10


def _minimal(**overrides) -> dict:
    spec = {"engine": "voxel", "duration_seconds": 5, "camera": {"shots": [{"time": 0, "location": [0, -5, 2]}]}}
    return {**spec, **overrides}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"engine": "unreal"}, "engine"),
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


def test_voxel_face_culling():
    grid = VoxelGrid()
    grid.set((0, 0, 0), "stone")
    assert len(list(grid.exposed_faces())) == 6
    grid.set((1, 0, 0), "stone")
    assert len(list(grid.exposed_faces())) == 10  # shared face hidden on both blocks
    grid.set((0, 1, 0), "water")
    faces = list(grid.exposed_faces(frozenset({"water"})))
    # The stone face behind the water stays visible; the water face touching stone is hidden.
    assert ((0, 0, 0), 2) in faces and ((0, 1, 0), 3) not in faces


def test_block_hash_is_stable():
    assert block_hash((1, 2, 3)) == block_hash((1, 2, 3))
    assert 0 <= block_hash((5, -4, 9), 7) <= 1


def test_world_generation_is_deterministic_with_flat_clear_stage():
    path = ((-6.0, 3.0), (2.0, 1.0))
    a = generate_world(11, paths=[path])
    b = generate_world(11, paths=[path])
    assert a.terrain.blocks == b.terrain.blocks
    assert a.terrain.blocks != generate_world(12, paths=[path]).terrain.blocks
    for x in range(-5, 6):
        for y in range(-5, 6):
            if math.hypot(x, y) < 6:
                assert a.ground_z(x, y) == 0  # stage surface at z=0
                assert (x, y, 0) not in a.terrain  # nothing standing on the stage
    assert len(a.clouds) > 0 and len(a.decor) > 0


def test_voxel_models_are_consistent():
    bot = explorer_bot()
    assert all(part.parent is None or part.parent in bot for part in bot.values())
    used = {block for part in bot.values() for block in part.grid.blocks.values()}
    assert used <= set(BOT_PALETTE)
    assert set(chest()) == {"base", "lid"}
