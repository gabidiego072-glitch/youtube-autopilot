"""Topics are things you SEE happen, and built objects have a fixed shape (Nov 11: 'water stops being wet' and
'flexible glass' could not be shown; 'melting office tower' came out as a shapeless blob)."""

import copy

from app.services.ideas.generator import generate_ideas, is_abstract_property
from app.services.scenes.recipe_planner import concrete, design_objects
from tests.conftest import IDEAS_RESPONSE, StubAIProvider


def test_abstract_property_premises_are_dropped():
    data = copy.deepcopy(IDEAS_RESPONSE)
    good = data["ideas"][0]
    flagged = {**good, "premise": "¿Qué pasaría si llovieran meteoritos?", "kind": "property"}  # labelled property
    sneaky = {**good, "premise": "¿Qué pasaría si el agua dejara de mojar?", "kind": "event"}  # caught by wording
    data["ideas"] = [good, flagged, sneaky]
    ideas = generate_ideas(StubAIProvider([data]), count=3, language="es", existing_premises=[])
    assert [i.premise for i in ideas] == [good["premise"]]


def test_what_did_well_is_not_abstract():
    for title in (
        "¿Qué pasaría si la Tierra frenara en seco?",
        "¿Qué pasaría si todos los humanos cayeran dormidos a la vez?",
        "What if a T-rex walked into New York?",
        "¿Qué pasaría si ayudaras a todas las personas sin hogar?",
    ):
        assert not is_abstract_property(title), title
    for title in (
        "What if glass became flexible?",
        "¿Qué pasaría si los metales perdieran su conductividad?",
        "¿Qué pasaría si la gravedad disminuyera un 1 por ciento?",
    ):
        assert is_abstract_property(title), title


def test_only_things_with_a_fixed_shape_are_built():
    assert concrete("rocket") and concrete("vending machine") and concrete("lifeboat")
    assert not concrete("melting office tower") and not concrete("soft glass window")
    assert not concrete("rippling skyscraper") and not concrete("warped car windshield")
    ai = StubAIProvider([])  # no design call is made for the changing things
    picks = [{"object": "sagging glass bridge"}, {"object": "soft glass window loop"}, {"object": "T-rex"}]
    designs = design_objects(ai, picks)
    assert list(designs) == ["t-rex"] and not ai.calls


def test_what_happens_inside_the_body_is_not_a_topic():
    """Nov 12: 'your body stopped producing saliva': not one of 7 scenes could show its line."""
    assert is_abstract_property("¿Qué pasaría si tu cuerpo dejara de producir saliva desde hoy?")
    assert is_abstract_property("What if your body stopped making new cells?")
    assert not is_abstract_property("¿Qué pasaría si dejaras de dormir?")


def test_the_opening_is_not_a_strangers_face():
    from app.services.production.short import cold_open_scene

    stranger = {"recipe": "meet_person", "characters": [{"id": "p"}], "environment": {}, "actions": []}
    sleeper = {"recipe": "meet_person", "characters": [{"id": "p", "pose": "sit"}], "environment": {}, "actions": []}
    calm = {"recipe": "street_watch", "characters": [], "environment": {}, "actions": []}
    assert cold_open_scene([calm, stranger, calm], [0, 1, 2]) is None
    assert cold_open_scene([calm, sleeper, calm], [0, 1, 2]) == 1
