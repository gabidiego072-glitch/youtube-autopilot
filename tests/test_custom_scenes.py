"""Nov 23: scenes written by hand for one video (render_engines/custom) go through the pipeline untouched."""

import json
from pathlib import Path

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
