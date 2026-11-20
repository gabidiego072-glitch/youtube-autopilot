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

POV_SCRIPT_NOTE = """STYLE: EXPLAIN IT, AND SHOW EVERY THING YOU SAY (owner, Nov 18: "nothing of what the video says
is seen; explain it, but every thing must be seen, in the right place"). Like the most viewed Shorts of this
format.
- ONE SUBJECT, ONE CONTINUOUS JOURNEY (the owner's reference, Nov 18, "What if your car never stopped
  accelerating?": the same red car from a city street to the highway, the sound barrier, the sky, space; every
  step follows from the last, one big number grows the whole time). Keep the SAME place (one recipe, at most
  two) and the SAME subject in most scenes, and make the premise grow in it step by step with the events: the
  fire spreads, the water rises, people float higher. Never jump to an unrelated place (a café, an office) for
  one line.
- SHORT LINES: at most 10 words each, one step each ("BOOM. The sound barrier." "The sky turns black.").
- TIME JUMPS in the same place, said in the line ("Day ninety. The power dies." "Year three. You build a
  home."), a touch of dry humour ("At first? It's paradise." "Guest list: Steve." for a mannequin), and a TWIST
  in the last lines that changes everything (the calm sea pulls back: a tsunami; after ten years alone, a
  second person: the counter goes from 1 to 2, "For now."). From the owner's references (Nov 18).
- The 'hud' counter is the hero number of the premise (speed, height, temperature, water level, people
  floating), growing in every line; plain words.
- SHOT FIRST. For every scene, first choose its 'shot' from the 3D world below (recipe + event + room, people,
  gesture, object, time of day), then write the narration so that it says EXACTLY what that shot shows, plus
  the reason in half a sentence of plain science. The viewer must see every noun and verb of the line.
  Example: shot {{recipe: kitchen, event: fire}} -> "Si el aire tuviera el doble de oxígeno, la sartén de tu
  cocina ardería sola." Never a line whose main thing is not in its shot.
- Second person, present or conditional ("If..., your...", "Si..., tu..."), one step per line, escalating: your
  home, your street, your city, the whole planet. Words a 10-year-old understands.
- PLACES: only the ones the shot shows: your kitchen, your bedroom, a café, an office, a hospital ward, a
  classroom, a street or the river/sea of the video's city, a park, the Earth from space. Say the city's name
  at most once; NEVER name stations, neighbourhoods, bridges or buildings (they are not built in 3D).
- Each scene's 'hud' is a short on-screen counter of what the premise changes, plus the clock ({example}); it
  grows every line, in the narration's language, plain words.
- A companion is OPTIONAL: if one appears (visual_bible.companion), they are on screen in reaction scenes and
  may say 1-2 short lines ('speaker' = their name), always in the narration's language. 'phone' only if a
  message is shown; empty otherwise.
- The ending: the viewer's choice (visual_bible.choice, question at most 6 words, options at most 4 words
  each), asked in the last line, ending_type "question".
- EVERY line in the narration's language: narration, companion, phone, choice. Never copy the language of an
  example.
- The 3D world (choose shots only from here):
  RECIPES: wake_up (your bedroom at dawn), cafe_news (a café, the TV shows news), street_run (you run down the
  avenue, people around), street_watch (you stand on the sidewalk and watch the avenue), dark_room (night at
  home, the power is out), kitchen (your kitchen, a cup, the stove), waterfront (the river or sea promenade),
  theater, park (a city park), space (the Earth from space: only for the whole planet), meet_person (you walk
  up to one person), hand_action (your hand works a thing on a wall: alarm, button, tap, lever), reaction (a
  person across a table DOES the line: gesture throat, cover, point, wave, reach, jump, fall; the object on the
  table), room_view (a room: office, hospital, classroom, living_room, bedroom, kitchen, cafe).
  EVENTS (what happens in front of you, in any recipe): fire, smoke, explosion, flood (water rises), crack (the
  ground splits), collapse (a building comes down), float (people and the object lift off), fly (people are
  thrown through the air), freeze (frost covers the ground), meteor (a burning rock hits the street in front of
  you), meteor_far (it hits far away, fireball over the roofs), meteor_sky (it crosses the sky, still coming),
  dazed (you are dizzy after a blast), none.
  threat (streets): none, panic (everyone runs), fire, flood, collapse, zombies. people: busy, empty,
  rough_sleepers. object: any concrete thing, named plainly (croissant, glass, phone, rocket, tent).
- NEVER narrate what no shot can show: what happens inside the body (cells, organs, pain, hunger, feelings),
  smells, sounds, temperatures, microscopic or invisible things, numbers without a picture. Show their visible
  consequence with a shot instead ("the tap gives nothing", "people collapse in the street")."""

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


def planned_script(premise: str, language: str = "es") -> dict | None:
    """The full script written by hand (by Claude) for a planned topic, if it has one (Nov 18).

    A planned topic may carry "script": the same JSON a script writer returns (title_question, hook, scenes with
    narration, hud and shot, ending_type, ending_line, visual_bible). The pipeline then uses it as it is: Gemini
    neither writes nor rewrites it, and the storyboard is built from each line's shot.
    """
    for topic in planned_topics():
        if topic.get("premise") == premise and base(topic.get("language", "es")) == base(language):
            return topic.get("script") or None
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
        f"SETTING: {name}. Outdoor scenes happen in a street of {name} (style {city}). Say the city's name at "
        "most once and never name its stations, neighbourhoods, bridges or buildings: they are not built in 3D "
        "(Nov 18: 'Shinjuku station' and 'Westminster Bridge' were heard over a generic street)."
    )


def next_city(recent_cities: list[str]) -> str:
    """The city used least among the channel's recent videos (ties: the first in CITIES)."""
    counts = {city: recent_cities.count(city) for city in CITIES}
    return min(CITIES, key=lambda city: counts[city])
