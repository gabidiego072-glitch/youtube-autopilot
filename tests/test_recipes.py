"""Scene recipes: every recipe builds a valid scene at any length; doors and flashes join the places."""

import pytest

from app.services.scenes.recipe_planner import assemble, plan_with_recipes
from app.services.scenes.recipes import RECIPES, THREATS, build
from render_engines.core.spec import validate_spec


@pytest.mark.parametrize("recipe", RECIPES)
@pytest.mark.parametrize("duration", [2.5, 4.5, 9.0])
def test_every_recipe_builds_a_valid_scene(recipe, duration):
    for threat in THREATS:
        spec = build(recipe, duration, seed=7, city="paris", threat=threat, door_out=True, headline="Hola")
        validate_spec(spec)
        times = [s["time"] for s in spec["camera"]["shots"]]
        assert times == sorted(times) and times[0] == 0 and abs(times[-1] - duration) < 1e-6
        for action in spec["actions"]:
            assert all(0 <= action[k] <= duration + 1e-6 for k in ("start", "end", "at") if k in action)


def test_leaving_a_place_opens_a_door_and_flashes_into_the_next():
    picks = [
        {"recipe": "cafe_news", "threat": "none", "time_of_day": "day", "look": "normal", "headline": "Brote"},
        {"recipe": "street_run", "threat": "zombies", "time_of_day": "day", "look": "normal"},
        {"recipe": "street_run", "threat": "zombies", "time_of_day": "day", "look": "xray"},
        {"recipe": "bogus", "threat": "?", "time_of_day": "noon", "look": "?"},
    ]
    specs = assemble(picks, [4.0, 6.0, 5.0, 3.0], seed=10, city="tokyo")
    assert any(a["type"] == "open_door" for a in specs[0]["actions"])
    assert specs[1]["transition"] == "flash" and specs[1]["environment"]["style"] == "tokyo"
    assert specs[1]["seed"] == specs[2]["seed"]  # same recipe, same street
    assert specs[2]["look"] == "xray" and specs[2]["transition"] == "flash"
    assert specs[3]["recipe"] == "street_watch"  # unknown picks are repaired


def test_the_ai_only_picks_recipes(tmp_path):
    from tests.conftest import StubAIProvider

    ai = StubAIProvider(
        [{"scenes": [{"recipe": "wake_up", "threat": "zombies", "time_of_day": "dawn", "look": "normal"}]}]
    )
    specs = plan_with_recipes(
        ai, scenes=[{"narration": "Te despiertas.", "hud": "DÍA 1 · 07:00"}], durations=[4.0], seed=3
    )
    assert specs[0]["camera"]["pov"] and "wake_up" in ai.calls[0]["system"]
