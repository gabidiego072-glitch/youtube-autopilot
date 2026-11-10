"""Hand-made scene recipes: the shots that work, as code.

The free-form storyboard (the AI writing coordinates and camera paths) gives jumpy, badly framed scenes. Here the
AI only picks, for each line of narration, one recipe and a few simple choices (threat, time of day, look); the
recipe builds the whole scene the way it was designed and tested by hand: first-person camera paths at eye
level, people placed where the camera will meet them, doors that open between places, the horde behind you.

Every recipe takes the scene duration (the length of its voice line) and lays out its moments relative to it.
`door_out` asks a recipe to end by turning to a door and opening it (the next scene starts through it).
"""

from __future__ import annotations

import random

PALETTES = (
    {"body": "#355c7d", "accent": "#f2c14e", "skin": "#e0ac85", "hair": "#2d1e14"},
    {"body": "#c06c84", "accent": "#e8e8e8", "skin": "#8d5524", "hair": "#1b1b1b"},
    {"body": "#4a7c59", "accent": "#e07a3a", "skin": "#f1c27d", "hair": "#6b4423"},
    {"body": "#d9a400", "accent": "#3f88c5", "skin": "#c68642", "hair": "#b89778"},
    {"body": "#1f4e8c", "accent": "#e8e8e8", "skin": "#d9a27e", "hair": "#2d1e14"},
    {"body": "#7a4a3f", "accent": "#f2f2f2", "skin": "#6b4226", "hair": "#1b1b1b"},
)
RECIPES = (
    "wake_up",
    "cafe_news",
    "street_run",
    "street_watch",
    "dark_room",
    "kitchen",
    "waterfront",
    "theater",
    "park",
    "space",
    "meet_person",
    "room_view",
)
INDOOR = {"wake_up", "cafe_news", "dark_room", "kitchen", "theater", "room_view"}
THREATS = ("none", "zombies", "panic", "fire", "flood", "collapse")
PEOPLE = ("busy", "empty", "rough_sleepers")  # who is on the street
ITEMS = ("none", "phone", "key", "cup", "flashlight")  # what you hold in your hand
ROOMS = ("living_room", "kitchen", "bedroom", "office", "classroom", "cafe", "hospital")
TRENDS = ("none", "up", "down")
SUBJECTS = ("sitting", "standing")
# Recipes whose hands are free to hold something (the others already hold a phone, a cup or a torch).
FREE_HANDS = {"street_watch", "meet_person", "room_view", "waterfront", "park"}
# Spots along the north wall that no bench, tree, lamp or café terrace takes, in every city style.
WALL_SPOTS = (-14.0, -6.0, 2.0)
WALL_Y = 6.95
DOOR_Y = 7.27  # a door on the north facade of the street (BUILDING_LINE - 0.13)
CROSS_STREET = (5.0, 15.0)


def _base(duration: float, seed: int, env: dict) -> dict:
    return {
        "engine": "cinematic",
        "duration_seconds": round(duration, 3),
        "fps": 24,
        "seed": seed,
        "environment": env,
        "characters": [],
        "props": [],
        "actions": [],
        "captions": [],
    }


def _shot(t, loc, target, lens=24):
    return {
        "time": round(t, 3),
        "location": [round(v, 3) for v in loc],
        "target": [round(v, 3) for v in target],
        "lens": lens,
    }


def _person(cid, start, facing, rng, **extra):
    return {
        "id": cid,
        "start": [round(start[0], 2), round(start[1], 2)],
        "facing": facing,
        "palette": dict(rng.choice(PALETTES)),
        "hat": False,
        **extra,
    }


def build(
    recipe: str,
    duration: float,
    *,
    seed: int,
    city: str = "new_york",
    threat: str = "none",
    time_of_day: str = "day",
    look: str = "normal",
    door_out: bool = False,
    headline: str = "",
    people: str = "busy",
    item: str = "none",
    room: str = "office",
    subject: str = "sitting",
    stat: str = "",
    trend: str = "none",
    obj: dict | None = None,
) -> dict:
    """One full scene spec from a recipe. Unknown recipes fall back to street_watch.

    people, item, room, subject, stat and trend put the story's own things in the scene: people sleeping
    rough or an empty street, a key in your hand, the hospital the narration mentions, the person you meet,
    a big number (with an arrow up or down) for a fact."""
    rng = random.Random(seed)
    maker = BUILDERS.get(recipe, street_watch)
    spec = maker(
        duration,
        rng=rng,
        seed=seed,
        city=city,
        threat=threat,
        time_of_day=time_of_day,
        door_out=door_out,
        headline=headline,
        people=people if people in PEOPLE else "busy",
        room=room if room in ROOMS else "office",
        subject=subject if subject in SUBJECTS else "sitting",
    )
    if item in ITEMS and item != "none" and recipe in FREE_HANDS and spec["camera"].get("pov"):
        spec["camera"].setdefault("pov_item", item)
    if obj and obj.get("parts") and recipe != "meet_person":  # there the person you meet fills the view
        _add_object(spec, obj)
    if stat and stat.strip():
        _add_stat(spec, duration, stat.strip(), trend if trend in TRENDS else "none")
    _fit(spec, duration)
    if look and look != "normal":
        spec["look"] = look
    spec["recipe"] = recipe
    return spec


def _bed(kind: str, start: float, end: float, every: float = 2.0) -> list[dict]:
    """A looping sound (steps, breath, heartbeat) cued every `every` seconds between start and end."""
    out, t = [], start
    while t < end - 0.3:
        out.append({"type": kind, "at": round(t, 3)})
        t += every
    return out


def _fit(spec: dict, d: float) -> None:
    """Short voice lines squeeze a recipe: keep every moment inside the scene and the shots in order."""
    for action in spec["actions"]:
        for key in ("start", "end", "at"):
            if key in action:
                action[key] = round(min(max(0.0, action[key]), d), 3)
        if "start" in action and "end" in action and action["end"] < action["start"]:
            action["end"] = action["start"]
    cam = spec["camera"]
    shots = sorted(cam["shots"], key=lambda s: s["time"])
    inside = [s for s in shots if s["time"] < d - 0.05]
    last = dict(shots[-1], time=round(d, 3))
    cam["shots"] = [*inside, last] if inside else [dict(shots[0], time=0.0), last]
    cam["shots"][0]["time"] = 0.0
    for key in ("pov_pushes", "pov_sips"):
        if key in cam:
            cam[key] = [t for t in cam[key] if t < d]
    if "shakes" in cam:
        cam["shakes"] = [s for s in cam["shakes"] if s["start"] < d]
    if "power_out" in spec:
        spec["power_out"] = min(spec["power_out"], d * 0.9)
    spec["sfx"] = [e for e in spec.get("sfx", []) if 0 <= e["at"] < d]


# --- indoors -----------------------------------------------------------------------------------------
def wake_up(d, *, rng, seed, threat, time_of_day, door_out, **_):
    """Bedroom, first person: you open your eyes, sit up, look at the window, then the door opens."""
    env = {
        "type": "interior",
        "room": "bedroom",
        "time_of_day": "dawn" if time_of_day in ("day", "dawn") else time_of_day,
        "room_light": 40,
    }
    spec = _base(d, seed, env)
    spec["props"].append(
        {"id": "door", "type": "door", "location": [-1.2, -2.6, 0], "facing": 180, "width": 1.0, "height": 2.2}
    )
    t_door = max(1.2, d * 0.6)
    spec["actions"].append({"type": "open_door", "prop": "door", "start": t_door, "end": t_door + 0.8})
    spec["sfx"] = [{"type": "whoosh", "at": t_door}]
    if threat in ("zombies", "panic", "fire"):
        spec["sfx"] += _bed("heartbeat", t_door, d, 1.6)
    if threat == "zombies":
        spec["characters"].append(_person("z", (-1.2, -3.3), 0, rng, zombie=True))
        spec["actions"].append(
            {
                "type": "walk",
                "character": "z",
                "from": [-1.2, -3.3],
                "to": [-0.9, -1.7],
                "start": t_door + 0.3,
                "end": d,
            }
        )
    spec["camera"] = {
        "pov": True,
        "pov_item": "phone",
        "handheld": 0.01,
        "fstop": 8.0,
        "shots": [
            _shot(0, (1.6, 1.9, 0.85), (1.4, -1.5, 2.6)),
            _shot(d * 0.28, (1.5, 1.55, 1.2), (0.0, 2.9, 1.5)),
            _shot(d * 0.5, (1.45, 1.35, 1.3), (-0.4, 2.9, 1.45)),
            _shot(t_door + 0.2, (1.4, 1.3, 1.32), (-1.2, -2.6, 1.4), 26),
            _shot(d, (1.35, 1.25, 1.32), (-1.0, -1.9, 1.5), 28),
        ],
        "shakes": [{"start": t_door, "end": t_door + 0.3, "strength": 0.02}],
    }
    return spec


def cafe_news(d, *, rng, seed, time_of_day, door_out, headline, **_):
    """Café, first person with a cup: the TV breaks the news; optionally you walk out through the door."""
    env = {"type": "interior", "room": "cafe", "time_of_day": time_of_day if time_of_day != "night" else "dusk"}
    if headline:
        env["headline"] = headline[:40]
    spec = _base(d, seed, env)
    spec["characters"] += [
        _person("barista", (-2.1, 0.6), -90, rng),
        _person("guest", (2.3, 0.6), 200, rng),
    ]
    spec["actions"] += [
        {"type": "look_at", "character": "barista", "target": "camera", "start": 0.3},
        {"type": "turn", "character": "guest", "start": d * 0.4, "end": d * 0.4 + 0.5, "facing": -25},
        {"type": "turn", "character": "barista", "start": d * 0.38, "end": d * 0.38 + 0.5, "facing": -30},
        {"type": "raise_arm", "character": "guest", "side": "R", "start": d * 0.5, "end": d * 0.5 + 0.5, "hold": 0.8},
    ]
    shots = [
        _shot(0, (0.35, -1.6, 1.25), (-0.6, 2.6, 1.35), 22),
        _shot(d * 0.35, (0.35, -1.6, 1.25), (0.6, 2.6, 1.5), 22),
        _shot(d * 0.6, (0.4, -1.55, 1.3), (1.85, 2.6, 1.8), 28),
    ]
    if door_out:
        spec["props"].append(
            {"id": "door", "type": "door", "location": [1.2, -2.6, 0], "facing": 180, "width": 1.0, "height": 2.2}
        )
        t = max(d * 0.72, d - 1.3)
        spec["actions"].append({"type": "open_door", "prop": "door", "start": t + 0.4, "end": t + 1.0})
        spec["sfx"] = [{"type": "whoosh", "at": t + 0.4}]
        shots += [
            _shot(t + 0.3, (0.95, -1.45, 1.65), (1.2, -3.6, 1.55)),
            _shot(d, (1.2, -2.35, 1.65), (1.2, -5.0, 1.55)),
        ]
    else:
        shots.append(_shot(d, (0.45, -1.5, 1.35), (1.85, 2.6, 1.8), 30))
    spec["camera"] = {
        "pov": True,
        "pov_item": "cup",
        "pov_sips": [min(1.0, d * 0.2)],
        "handheld": 0.012,
        "fstop": 8.0,
        "shots": shots,
    }
    return spec


def dark_room(d, *, rng, seed, threat, door_out, **_):
    """Night, living room, flashlight: the power goes out, something moves in the dark."""
    env = {"type": "interior", "room": "living_room", "time_of_day": "night", "room_light": 110}
    spec = _base(d, seed, env)
    spec["power_out"] = round(d * 0.45, 3)
    spec["sfx"] = [{"type": "impact", "at": d * 0.45}, *_bed("heartbeat", d * 0.5, d, 1.6)]
    if threat in ("zombies", "panic"):
        spec["characters"].append(_person("z", (-2.4, 1.7), 180, rng, zombie=threat == "zombies"))
        spec["actions"].append(
            {"type": "walk", "character": "z", "from": [-2.4, 1.7], "to": [-0.3, 0.1], "start": d * 0.55, "end": d}
        )
    spec["camera"] = {
        "pov": True,
        "pov_item": "flashlight",
        "handheld": 0.015,
        "fstop": 8.0,
        "shots": [
            _shot(0, (0.4, -1.9, 1.6), (1.5, 2.7, 1.3)),
            _shot(d * 0.5, (0.35, -1.85, 1.6), (0.4, 2.7, 1.5)),
            _shot(d * 0.73, (0.3, -1.8, 1.6), (-0.5, 2.0, 1.4), 26),
            _shot(d, (0.3, -1.85, 1.6), (-0.1, 0.3, 1.5), 28),
        ],
        "shakes": [{"start": d * 0.45, "end": d * 0.45 + 0.3, "strength": 0.03}],
    }
    return spec


def kitchen(d, *, rng, seed, threat, time_of_day, **_):
    """Kitchen, first person with an empty cup: the tap, the window, what is running out."""
    env = {
        "type": "interior",
        "room": "kitchen",
        "time_of_day": time_of_day if time_of_day != "golden" else "day",
        "room_light": 30,
    }
    spec = _base(d, seed, env)
    if threat == "fire":
        spec["actions"].append({"type": "fire", "location": [-2.8, 0.6, 0.95], "start": d * 0.3, "end": d, "size": 1})
    spec["camera"] = {
        "pov": True,
        "pov_item": "cup",
        "handheld": 0.01,
        "fstop": 8.0,
        "shots": [
            _shot(0, (1.0, 0.2, 1.6), (1.65, 2.3, 1.0), 26),
            _shot(d * 0.42, (1.4, 1.2, 1.6), (1.65, 2.4, 0.95), 28),
            _shot(d * 0.7, (1.2, 1.0, 1.6), (0.0, 2.9, 1.6), 26),
            _shot(d, (1.0, 0.9, 1.6), (-0.2, 2.9, 1.65), 26),
        ],
    }
    return spec


def theater(d, *, rng, seed, threat, **_):
    """Broadway theatre, first person walking down the aisle towards the stage."""
    spec = _base(d, seed, {"type": "theater", "rake": 0.0, "audience_fill": 0.9})
    spec["characters"].append(_person("performer", (0, 6.5), 180, rng, elevation=1.1))
    spec["actions"] += [
        {
            "type": "raise_arm",
            "character": "performer",
            "side": "R",
            "start": d * 0.15,
            "end": d * 0.25,
            "hold": d * 0.2,
        },
        {
            "type": "raise_arm",
            "character": "performer",
            "side": "L",
            "start": d * 0.16,
            "end": d * 0.26,
            "hold": d * 0.2,
        },
        {"type": "look_at", "character": "performer", "target": "camera", "start": d * 0.6},
    ]
    spec["camera"] = {
        "pov": True,
        "handheld": 0.025,
        "fstop": 4.0,
        "shots": [
            _shot(0, (0, -10.5, 1.7), (0, 6, 2.6), 22),
            _shot(d * 0.5, (0, -7.5, 1.7), (0, 6.3, 2.4)),
            _shot(d, (0, -4.5, 1.7), (0, 6.5, 2.3), 28),
        ],
    }
    return spec


# --- outdoors ----------------------------------------------------------------------------------------
def _street_env(city, time_of_day, threat):
    env = {
        "type": "city",
        "style": city,
        "time_of_day": time_of_day,
        "crowd": 120,
        "onlookers": 25,
        "parked_cars": 8,
        "traffic": 8,
        "keep_clear_y": -0.65,
    }
    if threat == "zombies":
        env.update(zombies=18, traffic=0, crowd=60, panic=40)
    elif threat == "panic":
        env.update(panic=55, traffic=4)
    elif threat == "flood":
        env.update(wet=True)
    return env


def street_run(d, *, rng, seed, city, threat, time_of_day, door_out, **_):
    """Running down the avenue, first person, shoving people aside; the horde (or the crowd) behind you."""
    env = _street_env(city, time_of_day, threat)
    if threat == "zombies":
        env.update(chasers=24, chasers_from=-52.0, zombies=0)
    spec = _base(d, seed, env)
    speed, x0, y = 5.0, -40.0, -0.65
    x_end = x0 + speed * d
    shots = []
    t = 0.0
    while t < d - 0.01:
        x = x0 + speed * t
        shots.append(_shot(t, (x, y, 1.65), (x + 20, -0.6, 1.45)))
        t += 1.25
    pushes, t_push, k = [], 1.3, 0
    while t_push < d - (1.8 if door_out else 0.8):
        x = x0 + speed * t_push + 1.0
        cid = f"p{k}"
        spec["characters"].append(_person(cid, (x, -0.4 if k % 2 == 0 else -0.9), 180, rng))
        spec["actions"] += [
            {"type": "look_at", "character": cid, "target": "camera", "start": max(0.0, t_push - 1.4)},
            {
                "type": "raise_arm",
                "character": cid,
                "side": "L",
                "start": max(0.0, t_push - 0.8),
                "end": t_push - 0.3,
                "hold": 0.2,
            },
            {"type": "fall", "character": cid, "start": t_push + 0.1, "direction_deg": 60 if k % 2 == 0 else -60},
        ]
        pushes.append(round(t_push, 3))
        t_push += 2.5
        k += 1
    if threat == "zombies" and d >= 4.5:  # a look over your shoulder at the horde
        tb = d * 0.55
        xb = x0 + speed * tb
        shots = [s for s in shots if abs(s["time"] - tb) > 0.5]
        shots += [
            _shot(tb - 0.2, (xb - 1, y, 1.65), (xb - 25, -0.4, 1.5)),
            _shot(tb + 0.4, (xb + 2, y, 1.65), (xb - 22, -0.4, 1.5)),
            _shot(tb + 0.8, (xb + 4, y, 1.65), (xb + 24, -0.6, 1.45)),
        ]
    spec["sfx"] = [*_bed("steps", 0.0, d), *_bed("breath", 0.3, d), *[{"type": "impact", "at": p} for p in pushes]]
    if threat == "zombies":
        spec["sfx"] += _bed("heartbeat", 0.2, d, 1.6)
    if door_out:
        spec["sfx"].append({"type": "whoosh", "at": max(0.0, d - 1.0)})
        xd = x_end + 3.0
        if CROSS_STREET[0] <= xd <= CROSS_STREET[1]:
            xd = CROSS_STREET[1] + 2.0
        spec["props"].append(
            {
                "id": "door",
                "type": "door",
                "location": [xd, DOOR_Y, 0],
                "facing": 0,
                "width": 1.3,
                "height": 2.6,
                "color": "#1e1e22",
                "light_behind": True,
            }
        )
        spec["actions"].append({"type": "open_door", "prop": "door", "start": d - 1.0, "end": d - 0.4})
        env["clear_zones"] = [[xd - 5, xd + 5, 0, 7.4]]
        shots = [s for s in shots if s["time"] < d - 1.6]
        shots += [
            _shot(d - 1.5, (x_end - 4, y + 1.0, 1.65), (xd, 7.4, 2.4)),
            _shot(d - 0.7, (xd - 0.8, 4.2, 1.65), (xd, 7.6, 2.0)),
            _shot(d, (xd, 6.7, 1.65), (xd, 10.5, 1.65)),
        ]
    else:
        shots.append(_shot(d, (x_end, y, 1.65), (x_end + 20, -0.6, 1.45)))
    shots.sort(key=lambda s: s["time"])
    spec["camera"] = {
        "pov": True,
        "pov_run": True,
        "pov_pushes": pushes,
        "handheld": 0.03,
        "fstop": 5.6,
        "shots": shots,
        "shakes": [{"start": p, "end": p + 0.35, "strength": 0.06} for p in pushes],
    }
    return spec


def street_watch(d, *, rng, seed, city, threat, time_of_day, people="busy", **_):
    """Standing on the sidewalk, first person: you look up the avenue at what is happening."""
    env = _street_env(city, time_of_day, threat)
    _people(env, people)
    spec = _base(d, seed, env)
    if people == "rough_sleepers" and threat == "none":  # look at the people sleeping along the wall
        _rough_sleepers(spec, rng)
        spec["camera"] = {
            "pov": True,
            "handheld": 0.02,
            "fstop": 5.6,
            "shots": [
                _shot(0, (-25.0, 5.0, 1.65), (-14.0, WALL_Y, 0.9), 24),
                _shot(d * 0.5, (-23.5, 5.15, 1.65), (-8.0, WALL_Y, 0.9), 24),
                _shot(d, (-22.0, 5.3, 1.65), (-2.0, WALL_Y, 1.0), 26),
            ],
        }
        spec["sfx"] = _bed("steps", 0.0, d, 0.6)
        return spec
    focus = (12.0, 7.0, 4.0)
    if threat == "fire":
        spec["actions"].append({"type": "fire", "location": [10.0, 6.4, 0.0], "start": 0.0, "end": d, "size": 3})
    elif threat == "collapse":
        spec["actions"].append({"type": "collapse", "x": 22.0, "start": d * 0.25, "end": d})
        spec["sfx"] = [{"type": "rumble", "at": d * 0.25}, {"type": "impact", "at": d * 0.3}]
        focus = (22.0, 12.0, 14.0)
    elif threat == "flood":
        spec["actions"].append({"type": "flood", "start": 0.0, "end": d, "height": 0.8})
        focus = (10.0, 0.0, 0.6)
    elif threat == "zombies":
        focus = (12.0, 0.0, 1.5)
    spec["camera"] = {
        "pov": True,
        "handheld": 0.02,
        "fstop": 5.6,
        "shots": [
            _shot(0, (-22.0, -5.2, 1.65), (focus[0] - 12, focus[1] - 4, focus[2] + 2), 24),
            _shot(d * 0.5, (-21.2, -5.0, 1.65), (focus[0] - 4, focus[1] - 1, focus[2] + 1), 24),
            _shot(d, (-20.4, -4.8, 1.65), focus, 28),
        ],
        "shakes": [{"start": d * 0.3, "end": d * 0.3 + 0.4, "strength": 0.04}] if threat == "collapse" else [],
    }
    return spec


def waterfront(d, *, rng, seed, city, threat, time_of_day, **_):
    """The river or the sea: you look at the water, then turn to what is coming."""
    env = {"type": "coast", "style": city, "time_of_day": time_of_day, "parked_cars": 6}
    if threat == "zombies":
        env["zombies"] = 22
    elif threat == "flood":
        env["wet"] = True
    spec = _base(d, seed, env)
    if threat == "flood":
        spec["actions"].append({"type": "surge", "start": d * 0.2, "end": d, "height": 1.2, "inland": 12})
    turn = d * 0.5
    spec["sfx"] = [{"type": "wind", "at": 0.0}]
    if threat == "zombies":
        spec["sfx"] += [{"type": "whoosh", "at": turn}, *_bed("heartbeat", turn, d, 1.6)]
    spec["camera"] = {
        "pov": True,
        "handheld": 0.015,
        "fstop": 5.6,
        "shots": [
            _shot(0, (0, -5.8, 1.75), (1.5, -40, -2.5)),
            _shot(turn - 0.3, (0.3, -6.4, 1.75), (-1.5, -40, -2.5)),
            _shot(turn + 0.6, (0.3, -6.5, 1.75), (-3.0, 4.0, 1.4)),
            _shot(d, (0.3, -6.6, 1.75), (-1.0, 3.0, 1.5), 30),
        ],
        "shakes": [{"start": turn + 0.4, "end": turn + 0.7, "strength": 0.02}],
    }
    return spec


def park(d, *, rng, seed, time_of_day, threat, **_):
    """A park on a sunny day (Central Park, Hyde Park...): people on the grass, you walk among them."""
    env = {
        "type": "meadow",
        "time_of_day": time_of_day if time_of_day in ("dawn", "day", "dusk") else "day",
        "trees": 14,
        "flowers": 40,
    }
    if threat == "zombies":
        env["zombies"] = 10
    spec = _base(d, seed, env)
    for k, (x, y) in enumerate(((-2.5, 6.0), (2.0, 8.5), (4.5, 5.0), (-5.0, 10.0))):
        cid = f"p{k}"
        spec["characters"].append(_person(cid, (x, y), rng.choice((150, 200, 240)), rng))
        spec["actions"].append(
            {
                "type": "wave" if k == 0 else "look_at",
                "character": cid,
                **(
                    {"side": "R", "start": d * 0.3, "end": d * 0.6}
                    if k == 0
                    else {"target": "camera", "start": d * 0.4}
                ),
            }
        )
    spec["camera"] = {
        "pov": True,
        "handheld": 0.015,
        "fstop": 5.6,
        "shots": [
            _shot(0, (0, -4.0, 1.65), (0, 8, 1.4), 24),
            _shot(d, (0.4, -1.0, 1.65), (1.0, 9, 1.5), 26),
        ],
    }
    return spec


def space(d, *, rng, seed, **_):
    """The whole Earth from space: what happens to the planet."""
    spec = _base(d, seed, {"type": "space", "stars": 0.8})
    spec["props"].append(
        {
            "id": "earth",
            "type": "planet",
            "location": [0, 0, 0],
            "radius": 6.0,
            "kind": "earth",
            "spin_rate": 6,
            "tilt": 18,
        }
    )
    spec["camera"] = {
        "pov": False,
        "fstop": 16,
        "shots": [
            _shot(0, (0, -22, 4), (0, 0, 0), 35),
            _shot(d, (4, -19, 5), (0, 0, 0), 38),
        ],
    }
    return spec


def _people(env: dict, people: str) -> None:
    """busy: the normal city; empty: nobody around; rough_sleepers: like busy (they are added by the recipe)."""
    if people == "empty":
        env.update(crowd=0, onlookers=0, panic=0, traffic=1, parked_cars=3)


def _rough_sleepers(spec: dict, rng, spots=WALL_SPOTS) -> None:
    """People sitting on cardboard against the north wall, with their sleeping bags and backpacks."""
    for k, x in enumerate(spots):
        cid = f"sleeper{k}"
        spec["props"].append(
            {
                "id": f"bed{k}",
                "type": "bedroll",
                "location": [x, WALL_Y, 0.0],
                "facing": 180,
                "seed": rng.randint(0, 99),
            }
        )
        palette = dict(rng.choice(PALETTES))
        palette["body"] = rng.choice(("#4a4a40", "#3a3f5c", "#5a4632", "#2f3440"))  # worn, dark clothes
        spec["characters"].append(_person(cid, (x, WALL_Y), 180, rng, pose="sit", hat=rng.random() < 0.5))
        spec["characters"][-1]["palette"] = palette
    env = spec["environment"]
    env["crowd_side"] = "south"  # nobody walks through them
    env["onlookers"] = 0


def _view(spec: dict):
    """Where the scene ends up looking: the camera's last position and its flat direction."""
    import math

    last = spec["camera"]["shots"][-1]
    loc, tgt = last["location"], last["target"]
    if isinstance(tgt, str):
        tgt = [loc[0], loc[1] + 6, loc[2]]
    dx, dy = tgt[0] - loc[0], tgt[1] - loc[1]
    n = math.hypot(dx, dy) or 1.0
    return loc, dx / n, dy / n


def _add_object(spec: dict, obj: dict, side: float = 0.0) -> None:
    """An AI-designed object (see app/services/scenes/objects.py) standing where you look, facing you."""
    import math

    loc, dx, dy = _view(spec)
    env_type = spec["environment"].get("type")
    height = float(obj.get("height", 1.0))
    if env_type == "interior":
        height = min(height, 2.0)
        dist, ground = 1.9, 0.0
    elif env_type == "space":
        dist, ground = 9.0, loc[2] - 1.0
        height = min(height, 4.0)
    else:
        # Far enough that the whole thing fits above eye level in the vertical frame.
        dist = min(90.0, max(4.5, (height - 1.6) / 0.4 + 2.5))
        ground = 0.0
    right = (dy, -dx)
    at = [loc[0] + dx * dist + right[0] * side, loc[1] + dy * dist + right[1] * side, ground]
    if env_type in ("city", "coast"):  # in the middle of the road, never inside a building
        at[1] = max(-2.0, min(2.0, at[1]))
        at[2] = -0.15
        last = spec["camera"]["shots"][-1]
        if abs(last["location"][1]) > 3.0:  # step off the sidewalk: lamp posts and trees hide the view
            last["location"] = [last["location"][0], math.copysign(2.4, last["location"][1]), last["location"][2]]
    facing = math.degrees(math.atan2(-dy, -dx)) - 90  # its front (+y) towards the camera
    spec["props"].append(
        {
            "id": "obj",
            "type": "model",
            "location": [round(v, 3) for v in at],
            "facing": round(facing, 1),
            "height": round(height, 3),
            "parts": obj["parts"],
        }
    )
    spec["object_name"] = obj.get("name", "")
    if env_type != "space":  # the scene ends looking at it: big things are framed from below
        spec["camera"]["shots"][-1]["target"] = [round(at[0], 3), round(at[1], 3), round(at[2] + height * 0.45, 3)]


def _add_stat(spec: dict, d: float, text: str, trend: str) -> None:
    """A big number or a short fact floating in the scene where you look, with an arrow up or down."""
    import math

    shots = spec["camera"]["shots"]
    last = shots[-1]
    loc, tgt = last["location"], last["target"]
    if isinstance(tgt, str):
        tgt = [loc[0], loc[1] + 6, loc[2]]
    dx, dy = tgt[0] - loc[0], tgt[1] - loc[1]
    n = math.hypot(dx, dy) or 1.0
    dx, dy = dx / n, dy / n
    indoor = spec["environment"].get("type") == "interior"
    dist, size = (2.3, 0.4) if indoor else (8.0, 1.1)
    text = text[:12]
    size = min(size, 0.7 * dist / max(1, len(text)))  # the whole text fits in the vertical frame
    at = [loc[0] + dx * dist, loc[1] + dy * dist, loc[2] + (0.5 if indoor else 1.4)]
    model = next((p for p in spec["props"] if p.get("id") == "obj"), None)
    if model is not None and model["height"] >= 3.0 and not indoor:  # below a big one, not over it
        at[2] = loc[2] - 0.1
    if model is not None and model["height"] < 3.0:  # the number floats above a small object, not over it
        at[2] = max(at[2], model["location"][2] + model["height"] + size * 0.8)
    appear = round(min(d * 0.2, max(0.0, d - 1.0)), 3)
    spec["props"].append(
        {
            "id": "stat",
            "type": "label",
            "location": [round(v, 3) for v in at],
            "text": text,
            "size": size,
            "color": "#ffffff",
        }
    )
    spec["actions"].append({"type": "appear", "target": "stat", "start": appear, "end": appear + 0.4})
    if trend in ("up", "down"):
        right = (dy, -dx)
        off = size * 0.33 * len(text) + size * 0.7
        z = at[2] + (size * 0.7 if trend == "down" else -size * 0.7)
        spec["props"].append(
            {
                "id": "stat_arrow",
                "type": "arrow",
                "location": [round(at[0] + right[0] * off, 3), round(at[1] + right[1] * off, 3), round(z, 3)],
                "direction": [0, 0, -1 if trend == "down" else 1],
                "length": round(size * 1.4, 3),
                "thickness": round(size * 0.12, 3),
                "color": "#ff4d4d" if trend == "down" else "#3ee08a",
            }
        )
        spec["actions"].append({"type": "appear", "target": "stat_arrow", "start": appear + 0.3, "end": appear + 0.8})
    spec.setdefault("sfx", []).append({"type": "whoosh", "at": appear})


def meet_person(d, *, rng, seed, city, threat, time_of_day, subject, people, **_):
    """You walk along the sidewalk to someone (sitting on cardboard against the wall, or standing): they look
    up at you, your hand reaches out (to give them something), they take it and, if sitting, stand up."""
    env = _street_env(city, time_of_day, "none")
    env.update(crowd_side="south", onlookers=0, crowd=60, traffic=6)
    _people(env, people)
    spec = _base(d, seed, env)
    px = -16.0  # clear of benches, trees, lamps and terraces in every city style
    sitting = subject != "standing"
    py = WALL_Y if sitting else 6.2
    if sitting:
        spec["props"].append(
            {"id": "bed", "type": "bedroll", "location": [px, WALL_Y, 0.0], "facing": 180, "seed": rng.randint(0, 99)}
        )
    person = _person("p", (px, py), 180, rng, **({"pose": "sit"} if sitting else {}))
    if sitting:
        person["palette"]["body"] = rng.choice(("#4a4a40", "#3a3f5c", "#5a4632"))
    spec["characters"].append(person)
    arrive = d * 0.55
    give = min(d - 0.4, arrive + 0.3)
    head = 0.75 if sitting else 1.5
    spec["actions"] += [
        {"type": "look_at", "character": "p", "target": "camera", "start": max(0.0, arrive - 1.2)},
        {"type": "reach", "character": "p", "side": "right", "start": give, "end": min(d, give + 0.5)},
    ]
    if sitting and d >= 4.0:
        spec["actions"].append({"type": "stand_up", "character": "p", "start": d * 0.72, "end": min(d, d * 0.72 + 1.2)})
    x0 = px - 9.0
    spec["camera"] = {
        "pov": True,
        "handheld": 0.02,
        "fstop": 4.0,
        "pov_pushes": [round(give, 3)],
        "shots": [
            _shot(0, (x0, 5.4, 1.65), (px + 2, 6.4, 1.2), 24),
            _shot(arrive * 0.6, (x0 + 5.0, 5.3, 1.65), (px, py, head), 24),
            _shot(arrive, (px - 1.0, 4.95, 1.62), (px, py, head), 24),
            _shot(d, (px - 0.9, 4.85, 1.6), (px, py, 1.3 if sitting and d >= 4.0 else head), 24),
        ],
    }
    spec["sfx"] = [*_bed("steps", 0.0, arrive, 0.55), {"type": "chime", "at": round(give, 3)}]
    return spec


def room_view(d, *, rng, seed, room, people, threat, time_of_day, **_):
    """You stand in a room the story talks about (an office, a hospital ward, a classroom...) and look around."""
    env = {"type": "interior", "room": room, "time_of_day": time_of_day}
    spec = _base(d, seed, env)
    if people != "empty":
        for k, (x, y, f) in enumerate(((-0.75, 0.5, 200), (0.85, 0.3, 160))):
            spec["characters"].append(_person(f"r{k}", (x, y), f, rng))
            spec["actions"].append({"type": "look_at", "character": f"r{k}", "target": "camera", "start": d * 0.4})
    if threat == "fire":
        spec["actions"].append({"type": "smoke", "location": [2.0, 2.0, 2.2], "start": 0.0, "end": d})
    side = rng.choice((-1, 1))
    spec["camera"] = {
        "pov": True,
        "handheld": 0.015,
        "fstop": 4.0,
        "shots": [
            _shot(0, (0.4 * side, -2.3, 1.62), (1.6 * side, 1.6, 1.1), 22),
            _shot(d, (0.1 * side, -2.0, 1.62), (-0.6 * side, 1.8, 1.0), 22),
        ],
    }
    spec["sfx"] = _bed("steps", 0.0, d * 0.6, 0.6)
    return spec


BUILDERS = {
    "wake_up": wake_up,
    "cafe_news": cafe_news,
    "street_run": street_run,
    "street_watch": street_watch,
    "dark_room": dark_room,
    "kitchen": kitchen,
    "waterfront": waterfront,
    "theater": theater,
    "park": park,
    "space": space,
    "meet_person": meet_person,
    "room_view": room_view,
}

RECIPE_GUIDE = """Scene recipes (pick one per scene; the camera is always YOUR eyes):
- wake_up: your bedroom at dawn, you sit up with your phone; the door opens (threat zombies: one walks in).
- cafe_news: a café, coffee in hand, the TV shows breaking news (give a 2-5 word headline).
- street_run: you run down the city avenue shoving people aside (threat zombies: the horde chases you;
  panic: everyone runs).
- street_watch: you stand on the sidewalk and look up the avenue at an event (threat fire, collapse, flood,
  zombies coming, panic, or none for the busy city).
- dark_room: night at home, the power goes out, flashlight (threat zombies: one comes out of the dark).
- kitchen: your kitchen, an empty cup: food, water, gas running out (threat fire: the stove burns).
- waterfront: the river or the sea; you look at the water and turn (threat zombies: the horde; flood: the sea
  rises).
- theater: a packed Broadway theatre, you walk down the aisle to the stage.
- park: a big city park on a sunny day, people on the grass.
- space: the whole Earth seen from space (only for what happens to the whole planet).
- meet_person: you walk along the sidewalk to ONE person (subject sitting = someone sleeping rough on cardboard
  against the wall; standing = anyone) who looks up at you; your hand reaches out to them (item key: you hand
  them a key) and they take it; a sitting person then stands up. For meeting, helping or giving someone something.
- room_view: you stand in a room the line talks about (room: office, hospital, classroom, living_room, bedroom,
  kitchen, cafe); people empty = nobody there.
Extra choices for any scene (they put the story's OWN things on screen, use them):
- people: busy (normal city) | empty (nobody on the street) | rough_sleepers (people sleeping on cardboard
  along the wall; street_watch with threat none).
- item: what YOU hold (key, phone, cup, flashlight, or none) in street_watch, meet_person, room_view,
  waterfront, park.
- stat: when the line gives a number or a fact, at most 12 characters shown big in 3D ("-40%", "0", "x2"),
  in the narration's language; trend up or down adds a green or red arrow.
Rules: keep the story a journey through few places (2-4 recipes in a video, repeat a recipe rather than jumping
everywhere); start with the most striking recipe of the story when it fits; use look xray when physics changes
how the world looks (atoms, light, x-ray vision) and keep the same recipe as the previous scene."""
