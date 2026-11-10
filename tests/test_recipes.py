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
    specs = assemble([picks[1], *picks], [4.0, 4.0, 6.0, 5.0, 3.0], seed=10, city="tokyo")[1:]
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


def test_a_video_never_starts_in_a_calm_room():
    picks = [
        {"recipe": "wake_up", "threat": "none", "time_of_day": "dawn", "look": "normal"},
        {"recipe": "street_run", "threat": "zombies", "time_of_day": "day", "look": "normal"},
    ]
    first = assemble(picks, [4.0, 4.0], seed=1, city="new_york")[0]
    assert first["recipe"] == "street_watch" and first["environment"].get("zombies")


def _pick(recipe, **extra):
    return {"recipe": recipe, "threat": "none", "time_of_day": "day", "look": "normal", **extra}


def test_the_story_own_things_are_on_screen():
    """The homeless video showed five empty streets: now the scenes carry the people, the key and the numbers."""
    picks = [
        _pick("street_watch", people="rough_sleepers"),
        _pick("meet_person", subject="sitting", item="key"),
        _pick("room_view", room="hospital", people="empty", stat="-40%", trend="down"),
        _pick("street_watch", people="empty", stat="0"),
    ]
    specs = assemble(picks, [4.0, 5.5, 4.5, 3.0], seed=5, city="paris")
    sitting = [c for c in specs[0]["characters"] if c.get("pose") == "sit"]
    assert len(sitting) == 3 and sum(p["type"] == "bedroll" for p in specs[0]["props"]) == 3
    assert specs[0]["environment"]["crowd_side"] == "south"  # nobody walks through them
    meet = specs[1]
    assert meet["camera"]["pov_item"] == "key" and meet["camera"]["pov_pushes"]
    assert {a["type"] for a in meet["actions"]} >= {"look_at", "reach", "stand_up"}
    hospital = specs[2]
    assert hospital["environment"] == {**hospital["environment"], "type": "interior", "room": "hospital"}
    assert not hospital["characters"]  # people empty: an empty ward
    labels = {p["id"]: p for p in hospital["props"]}
    assert labels["stat"]["text"] == "-40%" and labels["stat_arrow"]["direction"] == [0, 0, -1]
    assert specs[3]["environment"]["crowd"] == 0 and any(p["id"] == "stat" for p in specs[3]["props"])


def test_a_story_without_a_threat_opens_on_its_own_subject():
    picks = [_pick("kitchen"), _pick("cafe_news"), _pick("meet_person", subject="sitting", stat="x2")]
    first = assemble(picks, [4.0, 4.0, 5.0], seed=2, city="london")[0]
    assert first["recipe"] == "meet_person" and not first["environment"].get("panic")
    assert not any(p["id"] == "stat" for p in first["props"])


def test_long_stats_still_fit_the_frame():
    spec = build("room_view", 4.0, seed=1, room="office", stat="ALQUILER < CALLE")
    label = next(p for p in spec["props"] if p["id"] == "stat")
    assert len(label["text"]) <= 12 and label["size"] * len(label["text"]) <= 0.7 * 2.3 + 1e-6


def test_bad_choices_are_repaired():
    spec = assemble(
        [_pick("meet_person", people="?", item="sword", room="moon", subject="?", trend="?", stat=None)],
        [4.0],
        seed=1,
        city="paris",
    )[0]
    assert "pov_item" not in spec["camera"] and spec["characters"][0].get("pose") == "sit"


def test_missing_things_are_designed_and_built():
    """A thing no recipe shows (a rocket) is designed by the AI from shapes and stands where you look."""
    from app.services.scenes.objects import clean_design
    from tests.conftest import StubAIProvider

    rocket = {
        "height": 30,
        "parts": [
            {"shape": "cylinder", "size": [3, 3, 20], "at": [0, 0, 12], "color": "#e8e8ec"},
            {"shape": "cone", "size": [3, 3, 6], "at": [0, 0, 25], "color": "#c0392b"},
            {"shape": "teapot", "size": "big", "at": [0], "color": "red", "glow": "x"},
        ],
    }
    ai = StubAIProvider(
        [
            {"scenes": [{**_pick("street_watch"), "object": " Rocket ", "stat": "3..2..1"}, _pick("park")]},
            rocket,
        ]
    )
    specs = plan_with_recipes(ai, scenes=[{"narration": "Despega."}, {"narration": "Calma."}], durations=[5, 4], seed=1)
    assert "Object: rocket" in ai.calls[1]["prompt"]
    model = next(p for p in specs[0]["props"] if p["type"] == "model")
    validate_spec(specs[0])
    assert abs(model["location"][1]) <= 2.0 and model["height"] == 30  # on the road, real size
    assert specs[0]["camera"]["shots"][-1]["target"][:2] == model["location"][:2]  # you end up looking at it
    assert model["parts"][2] == clean_design(rocket)["parts"][2]  # nonsense is repaired, not fatal
    assert model["parts"][2]["shape"] == "box" and model["parts"][2]["color"] == "#9a9a9a"
    assert not any(p["type"] == "model" for p in specs[1]["props"])


def test_a_failed_design_leaves_the_scene_without_the_object():
    from tests.conftest import StubAIProvider

    ai = StubAIProvider([{"scenes": [{**_pick("park"), "object": "dragon"}]}, {"height": 3, "parts": []}])
    spec = plan_with_recipes(ai, scenes=[{"narration": "Un dragón."}], durations=[4], seed=1)[0]
    assert not any(p["type"] == "model" for p in spec["props"])
