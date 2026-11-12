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

POV_SCRIPT_NOTE = """STYLE: first-person POV ("what if it were YOU"), written like the channel's best hand-made videos.
- The FIRST line drops the viewer into the most dramatic moment of the story (in medias res): never start by
  waking up, a calm room or an explanation. TikTok data: viewers who see nothing happen leave within 7 seconds.
- Narrate in second person, present tense, as a JOURNEY with decisions: {lines}.
- Words a 10-year-old understands, in the narration and on screen: never medical or scientific jargon
  ("xerostomía", "enzimas salivales", "modulus"); say what it means ("tu boca se queda seca").
- ONE LINE = ONE THING YOU SEE HAPPEN in front of you, in at most 16 words: a person, a place, an object, a
  change you could film. Never abstract sentences ("studies show...", "the economy...", "this means...",
  "experts estimate..."): turn every fact into an image you see, with its number ("The ER waiting room is
  empty: cold injuries, minus 40%"). If it cannot be filmed, it does not go in the video.
- The story has a GOAL with a number, said in the hook in a few words (e.g. {goal}, "reach the river before
  night", "keep the lights on for 24 hours"): the viewer stays to see if they make it.
- Each scene's 'hud' is the on-screen counter. It measures what the premise changes, plus the clock: the sea
  level ("+30 m · 11:00"), the temperature, your speed, the people helped ("1/1000"), the days ({example}).
  It grows every line, short, in the narration's language, with words a 10-year-old understands (never
  technical terms or units like "MODULUS", "PPM", "kPa"). Time only moves forward; jump hours and days to
  keep the pace. For a counter in days the first scene starts at {first}. Never write words like LOOP or END
  in it: the last scene shows the final value.
- Escalate every line: a bigger number, a new place or a stranger event; never two lines that show the same
  thing. Around two thirds in, one turn ("and the worst hasn't come yet"), then the most extreme image.
- Name real places of the city in at least half of the lines (its streets, landmarks, the river, the metro).
- A PERSONAL STORY, not a list of facts: you live it with ONE companion (visual_bible.companion: a common
  first name in the narration's language, gender, relation: best friend, sister, dad, flatmate...). The
  companion SPEAKS 2-4 lines in their own voice: that scene's 'speaker' is their name and its narration is what
  they say, natural and short ("No abras la puerta.", "Te lo dije."). Every other line has speaker "narrator"
  (second person). Most of the story happens in one or two places with the same people.
- Your phone: 2-3 lines carry a text message from the companion in 'phone' (at most 8 words, like a real
  chat: lowercase, no full stop, e.g. "estoy en el súper. no queda agua"); empty otherwise.
- The ending is the viewer's CHOICE (this video is part 1): visual_bible.choice = question (at most 6 words)
  and two tempting options a and b (at most 4 words each). The last line asks it in the story ("¿Abres la
  puerta o esperas?") and ending_type is "question".
- Keep the science: each decision is explained in half a sentence with a real fact (how fast an outbreak
  spreads, how long the water and the power last without workers, how long a person lasts without water).
- WRITE ONLY WHAT THE 3D WORLD CAN SHOW. Every line is one of these moments, and the 'visual' names it:
  you walk, run or stand in a city street (busy, empty, people sleeping rough, panic, a fire, a flood, a
  building collapsing, a zombie horde, the story's text on every screen and billboard); you meet one person and
  hand them something; your hand works a thing on a wall (pull an alarm, press a button, open a tap, pull a
  lever); a room (home, kitchen, office, hospital ward, classroom, café with the TV news, theatre); the river
  or the sea rising; a park; dinosaurs; the Earth from space; your own hands changing (old, glowing); a big
  number floating in the air; any object, named plainly (a rocket, a tent, a vending machine).
- NEVER narrate what cannot be filmed in that world: liquids or materials behaving strangely, what happens
  inside your body (cells, organs, pain, thirst, hunger, feelings), smells, sounds, temperatures, microscopic
  or invisible things, abstract statistics. Show their visible consequence instead ("the tap gives nothing",
  "people queue at the hospital", "every screen says NO WATER")."""

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
