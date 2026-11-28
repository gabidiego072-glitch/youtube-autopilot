"""Nov 23: scenes written by hand for one video (render_engines/custom) go through the pipeline untouched."""

import json
from pathlib import Path

import pytest

from app.services.scenes.recipe_planner import SHOT_DEFAULTS, assemble, plan_from_shots
from render_engines.core.spec import validate_spec


def test_a_custom_shot_keeps_its_module_and_params():
    pick = {**SHOT_DEFAULTS, "recipe": "custom", "module": "steps", "params": {"start": 4.5, "stride": 6}}
    spec = assemble([pick], [2.8], seed=1, city="new_york", objects={}, companion=None, speaking=[False])[0]
    assert spec["custom"] == {"module": "steps", "params": {"start": 4.5, "stride": 6}}
    validate_spec({k: v for k, v in spec.items() if k not in ("pick",)})


def test_the_steps_video_is_one_continuous_path():
    topics = json.loads(Path("app/content/planned_topics.json").read_text(encoding="utf-8"))
    for topic in [t for t in topics if "steps" in json.dumps(t.get("script", {}))]:
        params = [s["shot"]["params"] for s in topic["script"]["scenes"]]
        for a, b in zip(params, params[1:], strict=False):
            assert b["start"] >= a["start"] + a["stride"] - 1e-6  # each leap starts at or after the last landing
        specs = plan_from_shots(None, scenes=topic["script"]["scenes"], durations=[2.8] * len(params), seed=3)
        assert specs and all(s.get("custom", {}).get("module") == "steps" for s in specs)


def test_the_ramp_scripts_pass_the_structure_rules_and_use_every_stage():
    from app.models.enums import VideoFormat
    from app.services.scripts.generator import ScriptDraft, structure_problems

    topics = json.loads(Path("app/content/planned_topics.json").read_text(encoding="utf-8"))
    ramp = [t for t in topics if '"module": "ramp"' in json.dumps(t.get("script", {}))]
    assert {t["language"] for t in ramp} == {"es", "en"}
    for topic in ramp:
        draft = ScriptDraft(**topic["script"], provider="claude", model="hand-written")
        assert structure_problems(draft, VideoFormat.SHORT, topic["language"]) == []
        stages = [s["shot"]["params"]["stage"] for s in topic["script"]["scenes"]]
        assert len(set(stages)) == len(stages) == 13
        specs = plan_from_shots(None, scenes=topic["script"]["scenes"], durations=[2.8] * 13, seed=3)
        assert all(s.get("custom", {}).get("module") == "ramp" for s in specs)


@pytest.mark.parametrize(
    ("module", "language", "count"),
    [
        ("balloons", "es", 12),
        ("zipline", "en", 11),
        ("trampoline", "es", 10),
        ("bouncyballs", "en", 10),
        ("wheels", "es", 10),
        ("umbrella", "en", 10),
        ("elevator", "es", 10),
        ("doors", "en", 9),
    ],
)
def test_the_nov26_scripts_pass_the_structure_rules_and_use_every_stage(module, language, count):
    from app.models.enums import VideoFormat
    from app.services.scripts.generator import ScriptDraft, structure_problems

    topics = json.loads(Path("app/content/planned_topics.json").read_text(encoding="utf-8"))
    mine = [t for t in topics if f'"module": "{module}"' in json.dumps(t.get("script", {}))]
    assert [t["language"] for t in mine] == [language]  # a different idea for each channel
    topic = mine[0]
    draft = ScriptDraft(**topic["script"], provider="claude", model="hand-written")
    assert structure_problems(draft, VideoFormat.SHORT, topic["language"]) == []
    stages = [s["shot"]["params"]["stage"] for s in topic["script"]["scenes"]]
    assert len(set(stages)) == len(stages) == count
    source = Path(f"render_engines/custom/{module}.py").read_text(encoding="utf-8")
    assert all(f'"{stage}"' in source for stage in stages)
    specs = plan_from_shots(None, scenes=topic["script"]["scenes"], durations=[2.8] * count, seed=3)
    assert all(s.get("custom", {}).get("module") == module for s in specs)
