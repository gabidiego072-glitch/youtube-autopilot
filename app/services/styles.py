"""Video styles beyond the classic third-person explainer, and topics planned by hand.

- planned topics (app/content/planned_topics.json) are used, in order, before any generated idea;
  each one is used once (a project with the same premise already exists = used).
- the 'pov' style: the viewer IS the protagonist. First-person camera with their own hands on screen, a
  second-person story told as a journey, and an on-screen counter (day and time) that keeps people
  watching to see how far they get.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.language import POV_VOICE, base

PLANNED_TOPICS = Path(__file__).resolve().parent.parent / "content" / "planned_topics.json"
STYLES = ("classic", "pov")

POV_SCRIPT_NOTE = """STYLE: first-person POV ("what if it were YOU").
- The FIRST line drops the viewer into the most dramatic moment of the story (in medias res): never start by
  waking up, a calm room or an explanation. TikTok data: viewers who see nothing happen leave within 7 seconds.
- Narrate in second person, present tense, as a survival JOURNEY with decisions: {lines}.
  Every scene is a new moment of the story; move through only 2-4 places (home, the street, the river...).
- The story has a GOAL with a number, said in the hook in a few words (e.g. {goal}, "reach the river before
  night", "keep the lights on for 24 hours"): the viewer stays to see if they make it.
- Each scene's 'hud' is the on-screen counter towards that goal: day out of the total and clock time, short,
  e.g. {example} (in the narration's language). Time only moves forward; jump hours and days to keep the
  pace. The first scene starts at {first} (N = the goal's number of days; for a goal in hours use the hour).
- The last line closes a loop: it leads straight back into the first line (e.g. it ends {loop}), so the
  video can be watched again and again.
- Keep the science: each decision is explained in half a sentence with a real fact (how fast an outbreak
  spreads, how long the water and the power last without workers, how long a person lasts without water).
- The 'visual' describes what YOU see in first person (your hands, your phone, the door in front of you)."""

POV_STORYBOARD_NOTE = """STYLE: first-person POV. In EVERY scene set camera.pov true: the camera is the viewer's
eyes at height 1.6 standing where the protagonist is, lens 22-28, moving a little forward as if walking. Use
pov_item phone when the narration mentions the phone or a map, flashlight in dark places. Do not draw the
protagonist as a character (the viewer is the protagonist); other people and zombies are characters."""


def pov_script_note(language: str = "es") -> str:
    lines, example, first, goal, loop = POV_VOICE[base(language)]
    return POV_SCRIPT_NOTE.format(lines=lines, example=example, first=first, goal=goal, loop=loop)


def planned_topics() -> list[dict]:
    try:
        return json.loads(PLANNED_TOPICS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def next_planned_topic(used_premises: set[str], language: str = "es") -> dict | None:
    """The first planned topic of this language not made yet (topics without 'language' are Spanish)."""
    for topic in planned_topics():
        if base(topic.get("language", "es")) != base(language):
            continue
        if topic.get("premise") and topic["premise"] not in used_premises:
            return topic
    return None


# Famous cities the 3D engine can build (city_style). Videos rotate through them: a recognisable place
# ("you are in Paris") keeps people watching more than a generic town.
CITIES = {
    "new_york": ("New York", "Times Square, Broadway, a Manhattan apartment, the subway, Central Park, the Hudson"),
    "paris": ("Paris", "the Eiffel Tower, a café terrace, the Champs-Élysées, the Seine, the Louvre, the metro"),
    "tokyo": ("Tokyo", "Shibuya crossing, Shinjuku's neon streets, Tokyo Tower, a convenience store, the train"),
    "london": ("London", "Big Ben, a red double-decker bus, the Thames, Piccadilly Circus, the Tube, a pub"),
}


def city_note(city: str) -> str:
    name, places = CITIES[city]
    return (
        f"SETTING: {name}. If the story happens in a city, it happens in {name}: name real places ({places}) "
        f"and use the city street with style {city} for every outdoor street scene."
    )


def next_city(recent_cities: list[str]) -> str:
    """The city used least among the channel's recent videos (ties: the first in CITIES)."""
    counts = {city: recent_cities.count(city) for city in CITIES}
    return min(CITIES, key=lambda city: counts[city])
