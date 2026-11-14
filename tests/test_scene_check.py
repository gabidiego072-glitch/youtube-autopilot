"""Every scene must SHOW what its narration says: scenes are looked at before the render, planned again when
they do not."""

from pathlib import Path

from app.services.scenes.check import check_scenes
from app.services.scenes.recipe_planner import assemble, replan
from render_engines.core.spec import validate_spec
from tests.conftest import StubAIProvider

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class FakeBlender:
    def __init__(self):
        self.specs = []

    def render_stills(self, spec_path: Path, out_dir: Path, fractions, aspect="9:16"):
        self.specs.append(spec_path.read_text())
        paths = []
        for n, _ in enumerate(fractions):
            p = out_dir / f"still_{n}.png"
            p.write_bytes(PNG)
            paths.append(p)
        return paths


def _pick(recipe, **extra):
    return {"recipe": recipe, "threat": "none", "time_of_day": "day", "look": "normal", **extra}


def test_scenes_are_judged_from_their_frames(tmp_path):
    specs = assemble([_pick("street_watch"), _pick("meet_person", item="key")], [4.0, 5.0], seed=1, city="paris")
    ai = StubAIProvider(
        [
            {"seen": "an empty Paris street", "shows_it": False, "missing": "the hospital"},
            {"seen": "you hand a key to a man on cardboard", "shows_it": True, "missing": ""},
        ]
    )
    blender = FakeBlender()
    verdicts = check_scenes(ai, blender, specs, ["Los hospitales se vacían.", "Le das la llave a Marc."], tmp_path, 7)
    assert verdicts[0]["shows_it"] is False and verdicts[1]["shows_it"] is True
    assert len(ai.calls[0]["images"]) == 2 and "Los hospitales" in ai.calls[0]["prompt"]


def test_a_failed_scene_is_planned_again_and_the_others_kept():
    specs = assemble([_pick("street_watch"), _pick("meet_person", item="key")], [4.0, 5.0], seed=1, city="paris")
    ai = StubAIProvider(
        [{"scenes": [_pick("room_view", room="hospital", people="empty", stat="-40%", trend="down"), _pick("park")]}]
    )
    new = replan(
        ai,
        specs=specs,
        scenes=[{"narration": "Los hospitales se vacían."}, {"narration": "Le das la llave."}],
        durations=[4.0, 5.0],
        feedback={0: "it shows an empty street; it needs the hospital"},
        seed=1,
        city="paris",
    )
    assert new[0]["environment"]["room"] == "hospital" and new[1]["recipe"] == "meet_person"  # scene 1 kept
    assert "it needs the hospital" in ai.calls[0]["prompt"]
    for spec in new:
        validate_spec(spec)


def test_a_long_look_at_the_planet_becomes_a_street():
    """Nov 11: the video failed because planet shots took 16% of it (the rule is 15%)."""
    picks = [_pick("street_run", threat="zombies")] * 5 + [_pick("space"), _pick("space")]
    specs = assemble(picks, [4.0] * 5 + [5.0, 5.0], seed=1, city="tokyo")
    assert [s["recipe"] for s in specs].count("space") == 0  # 5 s of 30 s is too long for one look
    short = assemble([_pick("street_watch")] * 6 + [_pick("space")], [5.0] * 6 + [3.0], seed=1, city="tokyo")
    assert short[-1]["recipe"] == "space"


def test_a_topic_whose_scenes_cannot_be_shown_is_dropped_before_the_render(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import pytest

    from app.services.autopilot import runner

    script = SimpleNamespace(scenes=[{"narration": f"line {i}"} for i in range(6)], visual_bible={})
    project = SimpleNamespace(id=SimpleNamespace(int=5), features={}, scripts=[script])
    monkeypatch.setattr(runner, "_project", lambda db, run: project)
    monkeypatch.setattr(runner, "_work_dir", lambda services, run: tmp_path)
    monkeypatch.setattr(runner, "replan", lambda ai, **kw: kw["specs"])
    services = SimpleNamespace(blender=None, log=lambda *_: None)

    def verdicts(passing):
        def fake(ai, blender, specs, lines, work, seed, only=None):
            return {i: {"seen": "", "shows_it": i in passing, "missing": ""} for i in (only or range(len(specs)))}

        return fake

    monkeypatch.setattr(runner, "check_scenes", verdicts({0, 1}))  # 2/6 even after replanning
    with pytest.raises(runner.StepBlocked):
        runner._show_what_is_said(None, None, services, None, [{}] * 6, [3.0] * 6, "")
    assert (tmp_path / "check" / "scene_check.json").exists()  # the report is kept to see why

    monkeypatch.setattr(runner, "check_scenes", verdicts({0, 1, 2}))  # 3/6: good enough, it is made
    specs, _ = runner._show_what_is_said(None, None, services, None, [{}] * 6, [3.0] * 6, "")
    assert len(specs) == 6
