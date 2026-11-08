"""What the 3D engine can draw and animate. Pure Python.

This is the single source of truth for (a) spec validation and (b) the prompt that
asks Claude to turn a script into scene specs, so the AI can only ask for things
the engine actually renders.
"""

ENVIRONMENTS = {
    "city": "Street at eye level: road (east-west, east = +x), sidewalks at z=0 (road is 0.15 m lower), buildings "
    "both sides (north side y > 7.4; a foreground 'hero' building near x=-6 has real glass windows), shops, "
    "awnings, street lamps, traffic lights, benches, bins, trees, parked cars, optional pedestrians. Options: "
    "time_of_day (dawn|day|golden|dusk|night), sun_azimuth, pedestrians (count), crowd (count of people "
    "walking on the sidewalks), panic (people running down the road), onlookers (people standing and staring), "
    "parked_cars, physics (true to let "
    "things be thrown; REQUIRED for inertia_shock and shatter_windows), style (old_town = narrow warm low "
    "houses | modern = tall grey/glass towers | suburb = 1-2 floor houses with roofs | new_york = Manhattan/Times "
    "Square towers with giant glowing billboards and yellow taxis | mixed). Keep the same "
    "style in every scene of a video.",
    "coast": "Seafront street: like 'city' but the south side is a promenade with a railing, a beach and the sea "
    "(water starts around y=-35). Use 'surge' to bring the sea into the street.",
    "interior": "A room (x in [-3,3], y in [-2.5,2.5], height 2.7; east wall at x=+3; window in the north "
    "wall at x in [-0.9,0.9]; keep people in the free centre |x|<1, -1.8<y<0.6). Option room: living_room "
    "(sofa, coffee table, bookshelf, TV) | kitchen (counter and stove on the west wall, stove at [-2.8,0.6,0.95], "
    "fridge, table with plates and cups) | bedroom (bed, wardrobe, desk) | office (desks, monitors, office chairs, "
    "whiteboard) | classroom (blackboard, pupil desks, backpacks) | cafe (counter with espresso machine, menu "
    "board, a TV with the news on the north wall at x 1.85, round tables with cups, hanging lamps). "
    "Pick the room the narration talks about. "
    "Other options: time_of_day, room_light (W), physics (true lets furniture, plates and books slide; REQUIRED "
    "for inertia_shock).",
    "meadow": "Outdoor countryside: hills, trees, rocks, flowers, sky. Options: time_of_day (dawn|day|dusk), "
    "trees, rocks, flowers, fireflies, hill_height. Characters stand on the ground at z=0 near the origin.",
    "theater": "Broadway theatre: stage at the north end (y 4-10, top at z 1.1, a performer stands at "
    "[0, 6.5]), golden arch, red curtains, footlights, a glowing sign; rows of red seats full of people in y "
    "[-9.5, 2.5] with a centre aisle at x 0; entrance doors at the back (y -12). Option audience_fill (0-1).",
    "space": "Outer space: black sky with stars, one sun light. Options: sun_azimuth, sun_elevation, stars "
    "(density 0-1). Use with planet props; there is no ground.",
}

# Which scene scales each environment can show (human-impact rule; see app/content/profile.py).
ENVIRONMENT_SCALES = {
    "city": ("street", "building", "vehicle", "crowd", "aerial"),
    "coast": ("street", "building", "vehicle", "crowd", "aerial"),
    "interior": ("interior",),
    "theater": ("interior", "crowd"),
    "meadow": ("street", "crowd", "aerial"),
    "space": ("global",),
}

PROPS = {
    "door": "a door in its frame; it opens with 'open_door' and bright daylight is behind it. Params: location "
    "[x,y,z] (bottom centre of the doorway), facing (deg; 0 = the viewer stands at -Y), width, height.",
    "theater_entrance": "city: a Broadway theatre front on the north side of the street (marquee with bulbs, "
    "glowing doors). Params: location [x, 0, 0] (only x is used).",
    "lantern_post": "Street lantern (2.3 m) that can be switched on. Params: location [x,y,z], facing (deg).",
    "planet": "Sphere world. Params: location [x,y,z], radius (m), kind (earth|moon|mars|sun), spin_rate (deg/s, "
    "default 0), tilt (deg), oceans_moved (0-1, earth only: start with oceans already at the poles). Earth has "
    "oceans, continents, ice caps, clouds and a blue atmosphere glow.",
    "arrow": "Glowing 3D arrow to show a direction or a speed. Params: location [x,y,z] (tail), direction [x,y,z], "
    "length (m), thickness (m), color (#RRGGBB). Use 'appear' to grow it in.",
    "label": "Short 3D text that always faces the camera (numbers, units, 1-4 words; never full sentences). "
    "Params: location [x,y,z], text, size (m), color.",
    "magnetic_field": "Glowing dipole field lines around a planet. Params: location (planet centre), radius "
    "(planet radius), color. Use 'fade' to weaken it.",
    "wind": "Wind streaks and flying leaves/rocks (meadow), still until a 'wind' action. Params: location "
    "[x,y,z] (centre), direction_deg (0 = towards +x / east), count, debris.",
}

ACTIONS = {
    "walk": "character walks: character, from [x,y], to [x,y], start, end, pace (steps/s, optional)",
    "grow": "character grows smoothly (time-lapse): character, start, end, to_scale (1 = normal 1.7 m person)",
    "turn": "character turns: character, start, end, facing (deg) or towards (id)",
    "raise_arm": "character raises an arm: character, side (left|right), start, end, hold (s)",
    "wave": "character waves: character, side, start, end",
    "jump": "character jumps: character, start, height (m)",
    "look_at": "character looks at an id or 'camera': character, target, start",
    "light_on": "switch a lantern on: prop, at",
    "spin": "change a planet's rotation speed: prop, start, end, rate_from (deg/s), rate_to (deg/s); after end the "
    "rate stays at rate_to",
    "scale": "scale a prop smoothly: target (prop id), start, end, factor (scale factor)",
    "appear": "a prop grows in from nothing: target, start, end",
    "fade": "a glowing prop (arrow, label, magnetic_field) fades to an opacity: target, start, end, to (0-1)",
    "fling": "inertia: a character is thrown through the air: character, start, end, direction_deg (0 = +x/east), "
    "speed (m/s), lift (m/s), gravity (m/s^2, low = slow-motion arc)",
    "wind": "start a wind prop: prop, start, end, speed (m/s)",
    "inertia_shock": "city/coast/interior with physics: the ground stops and everything loose (cars, benches, "
    "bins, furniture, books, glass) keeps moving: start, end, accel (m/s^2, ~20-60), direction_deg (0 = east)",
    "shatter_windows": "the hero building's windows break (glass shards fall; needs physics): start",
    "surge": "coast only: the sea rises and floods into the street: start, end, height (m), inland (m)",
    "lights_on": "city: street lamps and random windows switch on: start, end",
    "cover": "character crouches and covers the head: character, start, end",
    "fall": "character falls over: character, start, direction_deg",
    "open_door": "a door prop swings open: prop, start, end",
    "vanish": "magic trick: a puff of white smoke and the character disappears: character, start",
    "fire": "flames, flickering light and smoke: location [x,y,z] (default: the kitchen stove), start, end, size "
    "(1 = stove fire, 3 = a burning car)",
    "smoke": "dark smoke rising: location [x,y,z], start, end",
    "crack": "a crack grows: location [x,y,z] (on a wall: y=2.69 for the room's north wall; on the ground: z=0.01), "
    "start, end, surface (wall|floor), length (m)",
    "flood": "water rises in the room or the street: start, end, height (m; 0.3 = ankles, 1.0 = waist)",
    "collapse": "city/coast: the building nearest to x crumbles into dust: x (m), start, end",
    "sun_path": "meadow/city: the sun moves (time-lapse): start, end, elevation_from, elevation_to (deg; below 0 "
    "is night)",
    "migrate_oceans": "earth only: oceans flow to the poles, a continent rises at the equator: prop, start, end, "
    "amount (0-1)",
}

CHARACTERS = (
    "characters: {id, start [x,y], facing (deg), scale, zombie (true = grey-green zombie with arms forward and a "
    "lurching walk; use 'walk' to make it shamble towards someone)}. Environment option zombies (count) adds a "
    "horde that shambles in from the distance (city, coast, meadow; 2-3 inside a room)."
)

CAMERA = (
    "camera.shots: list of {time, location [x,y,z], target (id or [x,y,z]), lens (mm, 18-85)} in ascending time; "
    "the camera moves smoothly between shots and always aims at the target. Optional: fstop, handheld (0-0.05), "
    "shakes [{start, end, strength}] for impacts. Scene-level options: transition (cut|fade) into the scene, "
    "sfx [{type: whoosh|impact|rumble|wind|chime, at}] in scene seconds. First-person view: camera.pov true "
    "shows the viewer's own arms at the bottom of the frame (the viewer IS the protagonist): put the shots at eye "
    "height (z 1.6) where the protagonist is, lens 22-28, and optionally pov_item phone|flashlight; "
    "pov_run true when running (bobbing view, pumping arms); "
    "pov_pushes [seconds] when your hand shoves someone (pair it with that person's 'fall')."
)


def catalog_text() -> str:
    return "\n".join(
        [
            "Environments:",
            *(f"- {name}: {desc}" for name, desc in ENVIRONMENTS.items()),
            "Props:",
            *(f"- {name}: {desc}" for name, desc in PROPS.items()),
            "Characters: stylised person (hat, scarf). Params: id, start [x,y], facing (deg), scale, "
            "palette {body, skin, accent, hair} as #RRGGBB.",
            CHARACTERS,
            "Actions (times in seconds):",
            *(f"- {name}: {desc}" for name, desc in ACTIONS.items()),
            CAMERA,
        ]
    )
