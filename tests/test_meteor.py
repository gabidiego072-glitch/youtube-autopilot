"""Nov 20: a meteor the viewer can see (it falls along the street, in the frame) and parks full of trees."""

from app.services.scenes.recipes import EVENTS, build


def test_meteor_events_put_a_falling_rock_in_front_of_the_camera():
    for event in ("meteor", "meteor_far", "meteor_sky"):
        assert event in EVENTS
        spec = build("street_watch", 4.0, seed=1, city="new_york", time_of_day="dusk", event=event)
        rock = next(a for a in spec["actions"] if a["type"] == "meteor")
        assert rock["from"][2] > 40 and rock["lands"] == (event != "meteor_sky")
        shot = spec["camera"]["shots"][-1]
        ahead = (rock["location"][0] - shot["location"][0]) * (shot["target"][0] - shot["location"][0]) + (
            rock["location"][1] - shot["location"][1]
        ) * (shot["target"][1] - shot["location"][1])
        assert ahead > 0  # it lands (or passes) in front of you, not behind


def test_dazed_shakes_the_view_and_parks_have_many_trees():
    spec = build("street_watch", 3.0, seed=1, city="new_york", event="dazed")
    assert spec["camera"]["handheld"] > 0.05 and spec["camera"]["shakes"]
    assert build("park", 3.0, seed=1)["environment"]["trees"] >= 30
