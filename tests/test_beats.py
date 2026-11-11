"""One scene per sentence (Nov 11 audit): long lines are cut into beats, each beat gets its own scene inside the
line's clip, repeated places are framed anew, and bad numbers, crowds in the lens and washed-out frames go."""

from app.services.scenes.recipe_planner import assemble, plan_with_recipes
from app.services.scripts.beats import beats_for, split_line
from render_engines.core.spec import validate_spec
from tests.conftest import StubAIProvider


def _pick(recipe, **extra):
    return {"recipe": recipe, "threat": "none", "time_of_day": "day", "look": "normal", **extra}


def test_lines_are_cut_at_their_sentences_and_clauses():
    assert split_line("Te acercas a Marc bajo el puente del Sena y le entregas la llave de un estudio amueblado.") == [
        "Te acercas a Marc bajo el puente del Sena",
        "y le entregas la llave de un estudio amueblado.",
    ]
    # a short opening clause goes with what follows, never alone on screen
    pieces = split_line("Y lo peor aún no ha llegado: al sexto día, los centros de acogida empiezan a cerrar.")
    assert pieces[0] == "Y lo peor aún no ha llegado:" and pieces[1].startswith("al sexto día,")
    assert split_line("Corre.") == ["Corre."]
    text = "Uno dos tres cuatro cinco. Seis siete ocho nueve diez. Once doce trece catorce quince. Dieciséis a b c d."
    assert len(split_line(text)) <= 3 and " ".join(split_line(text)) == text  # never more than 3, no word lost


def test_the_ending_stays_whole_and_shares_add_up():
    scenes = [
        {"narration": "Estás en el puente de Westminster y el agua del Támesis rebota en tus dedos."},
        {"narration": "¿Sobrevivirías un solo día si el agua decidiera no tocarte jamás, ni una vez?"},
    ]
    beats = beats_for(scenes)
    assert [b["line"] for b in beats] == [0, 0, 1]
    assert abs(sum(b["share"] for b in beats if b["line"] == 0) - 1.0) < 1e-9


def test_every_beat_gets_its_own_scene_inside_the_line():
    scenes = [
        {"narration": "Te acercas a Marc bajo el puente del Sena y le entregas la llave de un estudio amueblado."},
        {"narration": "Y todo vuelve a empezar."},
    ]
    ai = StubAIProvider(
        [{"scenes": [_pick("street_watch", people="rough_sleepers"), _pick("meet_person", item="key"), _pick("park")]}]
    )
    specs = plan_with_recipes(ai, scenes=scenes, durations=[6.0, 2.0], seed=4, city="paris")
    assert len(specs) == 2  # still one spec per voice line
    line = specs[0]
    assert [p["recipe"] for p in line["parts"]] == ["street_watch", "meet_person"]
    assert abs(sum(line["shares"]) - 1.0) < 1e-9 and abs(line["duration_seconds"] - 6.0) < 0.01
    first_len = line["parts"][0]["duration_seconds"]
    assert any(e["at"] >= first_len for e in line["sfx"])  # the second piece's sounds come after the first
    assert "parts" not in specs[1] and "pieces of the same sentence" in ai.calls[0]["prompt"]
    for part in line["parts"]:
        validate_spec(part)


def test_the_same_place_is_framed_anew_every_time():
    """Nov 10: the homeless video showed one identical street shot for 31 s across four lines."""
    specs = assemble([_pick("street_watch")] * 4, [4.0] * 4, seed=9, city="paris")
    assert len({s["seed"] for s in specs}) == 1  # the same street...
    shots = {str(s["camera"]["shots"]) for s in specs}
    assert len(shots) == 4  # ...never the same shot


def test_clock_times_are_not_facts():
    specs = assemble(
        [_pick("street_watch", stat="08:00"), _pick("street_watch", stat="11h15"), _pick("street_watch", stat="-40%")],
        [3.0] * 3,
        seed=1,
        city="london",
    )
    shown = [next((p["text"] for p in s["props"] if p["id"] == "stat"), "") for s in specs]
    assert shown == ["", "", "-40%"]


def test_the_crowd_keeps_out_of_the_lens():
    from render_engines.cinematic import _camera_space

    avoid = _camera_space(
        {
            "pov": True,
            "shots": [
                {"time": 0, "location": [0, 0, 1.6], "target": [10, 0, 1.6]},
                {"time": 4, "location": [8, 0, 1.6], "target": [18, 0, 1.6]},
            ],
        },
        4.0,
    )
    assert avoid(0.5, 0.2, 0.0) and avoid(2.2, 0.0, 0.0)  # on you, right in front of you
    assert avoid(8.0, 0.5, 1.0) and not avoid(8.0, 0.5, 0.0)  # where you will be, but only then
    assert not avoid(0.0, 5.0, 0.0)  # on the far sidewalk


def test_a_line_of_27_words_is_rejected_in_a_short():
    from app.models.enums import VideoFormat
    from app.services.scripts.generator import ScriptDraft, structure_problems
    from tests.conftest import SCRIPT_RESPONSE

    data = {**SCRIPT_RESPONSE, "scenes": [dict(s) for s in SCRIPT_RESPONSE["scenes"]]}
    ok = ScriptDraft(**data, provider="t", model="t")
    assert not any("narration has" in p for p in structure_problems(ok, VideoFormat.SHORT))
    data["scenes"][1]["narration"] = " ".join(["palabra"] * 27)
    long = ScriptDraft(**data, provider="t", model="t")
    assert any("Scene 1 narration has 27 words" in p for p in structure_problems(long, VideoFormat.SHORT))


def test_each_piece_is_timed_to_its_share_of_the_voice():
    from app.services.editing.assembler import plan_timeline
    from app.services.production.modes import get_mode
    from app.services.production.short import timed_spec

    scenes = [
        {"narration": "Te acercas a Marc bajo el puente del Sena y le entregas la llave de un estudio."},
        {"narration": "Y todo vuelve a empezar."},
    ]
    ai = StubAIProvider([{"scenes": [_pick("street_watch"), _pick("meet_person", item="key"), _pick("park")]}])
    spec = plan_with_recipes(ai, scenes=scenes, durations=[6.0, 2.0], seed=4, city="paris")[0]
    slot = plan_timeline([5.0, 2.0], ["cut", "fade"], fps=24)[0]
    timed = timed_spec(spec, slot, 4, "draft")
    lengths = [p["duration_seconds"] for p in timed["parts"]]
    assert abs(sum(lengths) - slot.clip_length) < 0.01  # the pieces fill the line, plus the transition tail
    assert get_mode("draft") and all(
        p["camera"]["shots"][-1]["time"] <= p["duration_seconds"] + 1e-6 for p in timed["parts"]
    )
