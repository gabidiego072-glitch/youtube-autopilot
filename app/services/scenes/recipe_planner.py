"""Storyboard from recipes: the AI only picks a recipe and a few choices per scene; code builds the scenes.

Continuity is decided here, not by the AI: when the story leaves a place, the scene ends at a door that opens
and the next one starts through a white flash; a change of look (x-ray) flashes too; scenes that stay in the
same recipe reuse the same seed, so it is the same street or room.
"""

from __future__ import annotations

from app.content.profile import CHANNEL_CONCEPT
from app.core.errors import ProviderError
from app.services.ai.base import AIProvider
from app.services.scenes.recipes import BUILDERS, RECIPE_GUIDE, RECIPES, THREATS, build
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
                    "headline": {"type": "string"},
                },
                "required": ["recipe", "threat", "time_of_day", "look"],
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
Pick what each line SHOWS: if it says you run, street_run; the news, cafe_news; the lights go out, dark_room;
water or food running out, kitchen; the river or the sea, waterfront; the whole planet, space."""


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
    return assemble(picks, durations, seed=seed, city=city)


def assemble(picks: list[dict], durations: list[float], *, seed: int, city: str) -> list[dict]:
    """Build every scene from its recipe, with doors, flashes and shared places between scenes."""
    picks = [_clean(p) for p in picks]
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
        )
        if i:
            prev = picks[i - 1]
            through_door = prev["recipe"] in DOOR_EXITS and prev["recipe"] != recipe
            spec["transition"] = "flash" if through_door or prev["look"] != pick["look"] else "fade"
        try:
            specs.append(validate_spec(spec))
        except SpecError as exc:
            raise ProviderError(f"recipe {recipe} built an invalid scene: {exc}") from exc
    return specs


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
    return out
