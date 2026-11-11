"""Storyboard from recipes: the AI only picks a recipe and a few choices per scene; code builds the scenes.

Continuity is decided here, not by the AI: when the story leaves a place, the scene ends at a door that opens
and the next one starts through a white flash; a change of look (x-ray) flashes too; scenes that stay in the
same recipe reuse the same seed, so it is the same street or room.
"""

from __future__ import annotations

import json

from app.content.profile import CHANNEL_CONCEPT
from app.core.errors import ProviderError
from app.services.ai.base import AIProvider
from app.services.scenes.objects import design_object
from app.services.scenes.recipes import (
    BUILDERS,
    HANDS,
    ITEMS,
    PEOPLE,
    RECIPE_GUIDE,
    RECIPES,
    ROOMS,
    SUBJECTS,
    THREATS,
    TRENDS,
    build,
)
from render_engines.core.spec import SpecError, validate_spec

DOOR_EXITS = {"wake_up", "cafe_news", "street_run"}  # recipes that can end by opening a door
TIMES = ("dawn", "day", "golden", "dusk", "night")
RECIPE_SCHEMA = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "recipe": {"type": "string", "enum": list(RECIPES)},
                    "threat": {"type": "string", "enum": list(THREATS)},
                    "time_of_day": {"type": "string", "enum": list(TIMES)},
                    "look": {"type": "string", "enum": ["normal", "xray"]},
                    "people": {"type": "string", "enum": list(PEOPLE)},
                    "item": {"type": "string", "enum": list(ITEMS)},
                    "room": {"type": "string", "enum": list(ROOMS)},
                    "subject": {"type": "string", "enum": list(SUBJECTS)},
                    "stat": {"type": "string"},
                    "trend": {"type": "string", "enum": list(TRENDS)},
                    "hands": {"type": "string", "enum": list(HANDS)},
                    "headline": {"type": "string"},
                    "object": {"type": "string"},
                    "screens": {"type": "string"},
                },
                "required": ["recipe", "threat", "time_of_day", "look", "people", "item", "stat", "trend", "hands"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scenes"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = f"""You are the director of a first-person YouTube Shorts channel. {CHANNEL_CONCEPT}
The viewer IS the protagonist: every scene is seen through their eyes. You do not place cameras or objects:
for each narration line you pick one of the hand-made scene recipes below and a few choices.

{RECIPE_GUIDE}

Choices per scene: recipe; threat (none|zombies|panic|fire|flood|collapse) = what the scene shows happening;
time_of_day (dawn|day|golden|dusk|night) following the story's clock (the on-screen counter); look (normal, or
xray when the narration says the world itself changes how it looks); headline only for cafe_news (2-5 words in
the narration's language, e.g. the news the TV shows).
THE VIEWER MUST SEE WHAT THE NARRATION SAYS. A street where nothing related happens is a failure: every scene
shows the line's own subject (the person, the place, the object, the number).
Scene 0 is the hook: the most striking picture of the story (a threat if there is one: street_run,
street_watch with fire/collapse/flood/zombies, waterfront; otherwise the story's own subject: meet_person,
rough_sleepers...), never a calm room.
Pick what each line SHOWS: if it says you run, street_run; the news, cafe_news; the lights go out, dark_room;
water or food running out, kitchen; the river or the sea, waterfront; the whole planet, space; you meet, help or
give something to someone, meet_person; a hospital, an office, a school, room_view with that room; people
living on the street, people rough_sleepers; nobody left, people empty. A line with a number or a measurable
result gets a stat (the number itself, e.g. "-40%") and a trend.
If the line talks about a THING none of the above shows (a rocket, a dinosaur, a vending machine, a tent, a
giant coin...), name it in object (English, 1-3 words) and it will be built for that scene; leave object empty
otherwise. Never ask for people, cars, buildings, streets or rooms as an object: the recipes already have them.
Never use the same recipe with the same choices in more than 2 scenes in a row: the picture must move on with
the story. Every video must look NEW: when the notes list what recent videos already showed, prefer other
recipes, rooms, times of day, items and objects, and give this video at least one thing never seen before on
the channel (an object, a room, a moment)."""


def _scene_list(scenes: list[dict], durations: list[float]) -> str:
    return "\n".join(
        f"{i}. ({durations[i]:.1f}s) counter {s.get('hud', '') or '-'} | {s.get('narration', '')} | shows: "
        f"{s.get('visual', '')}"
        for i, s in enumerate(scenes)
    )


def plan_with_recipes(
    provider: AIProvider,
    *,
    scenes: list[dict],
    durations: list[float],
    seed: int,
    city: str = "new_york",
    notes: str | None = None,
) -> list[dict]:
    if len(scenes) != len(durations):
        raise ValueError("One duration per scene is required.")
    prompt = f"City of this video: {city}.\n\nScenes (index, length, counter, narration, what it shows):\n"
    prompt += _scene_list(scenes, durations)
    if notes:
        prompt += f"\n\n{notes}"
    result = provider.generate_json(system=SYSTEM_PROMPT, prompt=prompt, schema=RECIPE_SCHEMA)
    picks = result.data.get("scenes", [])
    if len(picks) != len(scenes):
        raise ProviderError(f"Recipe storyboard has {len(picks)} scenes; the script has {len(scenes)}.")
    return assemble(picks, durations, seed=seed, city=city, objects=design_objects(provider, picks))


def replan(
    provider: AIProvider,
    *,
    specs: list[dict],
    scenes: list[dict],
    durations: list[float],
    feedback: dict[int, str],
    seed: int,
    city: str = "new_york",
    notes: str | None = None,
) -> list[dict]:
    """Plan again the scenes that do not show their line (feedback: what the check saw and what is missing),
    keeping every other scene as it is."""
    picks = [dict(s.get("pick") or {}) for s in specs]
    prompt = f"City of this video: {city}.\n\nScenes (index, length, counter, narration, what it shows):\n"
    prompt += _scene_list(scenes, durations)
    prompt += "\n\nCurrent choices per scene:\n" + "\n".join(f"{i}. {json.dumps(p)}" for i, p in enumerate(picks))
    prompt += (
        "\n\nA reviewer looked at these scenes and they do NOT show what their line says. Choose again for every "
        "scene (return all of them, keep the others as they are), so the viewer SEES the line: another recipe, "
        "people, item, room, stat or an object to build.\n"
        + "\n".join(f"Scene {i}: {text}" for i, text in sorted(feedback.items()))
    )
    if notes:
        prompt += f"\n\n{notes}"
    result = provider.generate_json(system=SYSTEM_PROMPT, prompt=prompt, schema=RECIPE_SCHEMA)
    fresh = result.data.get("scenes", [])
    if len(fresh) != len(picks):
        raise ProviderError("The new storyboard does not have one choice per scene.")
    for i in feedback:
        picks[i] = fresh[i]
    return assemble(picks, durations, seed=seed, city=city, objects=design_objects(provider, picks))


MAX_OBJECTS = 3  # designs per video (one AI call each)


def design_objects(provider: AIProvider, picks: list[dict]) -> dict[str, dict]:
    """Design every thing the storyboard asked for that the engine has no model of (a few per video)."""
    names: list[str] = []
    for pick in picks:
        name = _object_name(pick.get("object"))
        if name and name not in names:
            names.append(name)
    designs = {}
    for name in names[:MAX_OBJECTS]:
        design = design_object(provider, name)
        if design is not None:
            designs[name] = design
    return designs


def _object_name(value) -> str:
    return " ".join(str(value or "").lower().split())[:40]


def assemble(
    picks: list[dict], durations: list[float], *, seed: int, city: str, objects: dict[str, dict] | None = None
) -> list[dict]:
    """Build every scene from its recipe, with doors, flashes and shared places between scenes."""
    picks = [_clean(p) for p in picks]
    _ration_stats(picks)
    _limit_space(picks, durations)
    _striking_start(picks)
    seeds: dict[str, int] = {}
    specs = []
    for i, (pick, duration) in enumerate(zip(picks, durations, strict=True)):
        recipe = pick["recipe"]
        seeds.setdefault(recipe, seed + 97 * (len(seeds) + 1))  # same recipe = same place
        nxt = picks[i + 1] if i + 1 < len(picks) else None
        door_out = bool(nxt) and recipe in DOOR_EXITS and nxt["recipe"] != recipe
        spec = build(
            recipe,
            duration,
            seed=seeds[recipe],
            city=city,
            threat=pick["threat"],
            time_of_day=pick["time_of_day"],
            look=pick["look"],
            door_out=door_out,
            headline=pick.get("headline", ""),
            people=pick["people"],
            item=pick["item"],
            room=pick["room"],
            subject=pick["subject"],
            stat=pick["stat"],
            trend=pick["trend"],
            obj=(objects or {}).get(_object_name(pick.get("object"))),
            hands=pick["hands"],
            screens=pick.get("screens", ""),
        )
        spec["pick"] = dict(pick)  # what the director chose, to plan this scene again if it fails the check
        if i:
            prev = picks[i - 1]
            through_door = prev["recipe"] in DOOR_EXITS and prev["recipe"] != recipe
            spec["transition"] = "flash" if through_door or prev["look"] != pick["look"] else "fade"
        try:
            specs.append(validate_spec(spec))
        except SpecError as exc:
            raise ProviderError(f"recipe {recipe} built an invalid scene: {exc}") from exc
    return specs


SLOW_STARTS = {"wake_up", "kitchen", "dark_room", "cafe_news", "theater", "park"}


def _striking_start(picks: list[dict]) -> None:
    """The first scene must grab the viewer. A calm room becomes the street with the story's main threat; a story
    without a threat opens instead on its own strongest picture (the person you meet, people sleeping rough)."""
    if not picks or picks[0]["recipe"] not in SLOW_STARTS:
        return
    threat = next((p["threat"] for p in picks if p["threat"] != "none"), None)
    if threat:
        picks[0] = {**picks[0], "recipe": "waterfront" if threat == "flood" else "street_watch", "threat": threat}
        return
    subject = next(
        (p for p in picks if p["recipe"] == "meet_person" or p["people"] == "rough_sleepers"),
        None,
    )
    if subject is not None:
        picks[0] = {**subject, "stat": "", "trend": "none"}
    else:
        picks[0] = {**picks[0], "recipe": "street_watch", "people": "busy"}


MAX_GLOBAL_SHARE = 0.14  # just under the human-impact rule (15%): the planet is a short moment, never more


def _limit_space(picks: list[dict], durations: list[float]) -> None:
    """At most one look at the whole planet, and only if it is short: the script check refuses more (a video
    failed on Nov 11 with 16% of planet shots after the storyboard had been made)."""
    total = sum(durations) or 1.0
    kept = False
    for pick, d in zip(picks, durations, strict=True):
        if pick["recipe"] != "space":
            continue
        if not kept and d / total <= MAX_GLOBAL_SHARE:
            kept = True
            continue
        pick["recipe"] = "street_watch"
        pick["people"] = "busy" if pick["people"] == "rough_sleepers" else pick["people"]


MAX_STATS = 3


def _ration_stats(picks: list[dict]) -> None:
    """Big 3D numbers are for real numbers, a few per video: the aging video put '+10' (the counter again)
    in every scene and 'LOOP' at the end."""
    kept, last = 0, None
    for pick in picks:
        stat = pick["stat"]
        if not any(ch.isdigit() for ch in stat) or stat == last or kept >= MAX_STATS:
            pick["stat"], pick["trend"] = "", "none"
            continue
        kept, last = kept + 1, stat


def _clean(pick: dict) -> dict:
    out = dict(pick)
    if out.get("recipe") not in BUILDERS:
        out["recipe"] = "street_watch"
    if out.get("threat") not in THREATS:
        out["threat"] = "none"
    if out.get("time_of_day") not in TIMES:
        out["time_of_day"] = "day"
    if out.get("look") not in ("normal", "xray"):
        out["look"] = "normal"
    for key, allowed, default in (
        ("people", PEOPLE, "busy"),
        ("item", ITEMS, "none"),
        ("room", ROOMS, "office"),
        ("subject", SUBJECTS, "sitting"),
        ("trend", TRENDS, "none"),
        ("hands", HANDS, "normal"),
    ):
        if out.get(key) not in allowed:
            out[key] = default
    out["stat"] = str(out.get("stat") or "").strip()[:12]
    out["screens"] = str(out.get("screens") or "").strip()[:28]
    return out
