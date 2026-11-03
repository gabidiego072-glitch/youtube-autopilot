"""What the 3D engine can draw and animate. Pure Python.

This is the single source of truth for (a) spec validation and (b) the prompt that
asks Claude to turn a script into scene specs, so the AI can only ask for things
the engine actually renders.
"""

ENVIRONMENTS = {
    "meadow": "Outdoor countryside: hills, trees, rocks, flowers, sky. Options: time_of_day (dawn|day|dusk), "
    "trees, rocks, flowers, fireflies, hill_height. Characters stand on the ground at z=0 near the origin.",
    "space": "Outer space: black sky with stars, one sun light. Options: sun_azimuth, sun_elevation, stars "
    "(density 0-1). Use with planet props; there is no ground.",
}

PROPS = {
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
    "sun_path": "meadow only: the sun moves (time-lapse): start, end, elevation_from, elevation_to (deg; below 0 "
    "is night)",
    "migrate_oceans": "earth only: oceans flow to the poles, a continent rises at the equator: prop, start, end, "
    "amount (0-1)",
}

CAMERA = (
    "camera.shots: list of {time, location [x,y,z], target (id or [x,y,z]), lens (mm, 18-85)} in ascending time; "
    "the camera moves smoothly between shots and always aims at the target. Optional: fstop, handheld (0-0.05), "
    "shakes [{start, end, strength}] for impacts. Scene-level options: transition (cut|fade) into the scene, "
    "sfx [{type: whoosh|impact|rumble|wind|chime, at}] in scene seconds."
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
            "Actions (times in seconds):",
            *(f"- {name}: {desc}" for name, desc in ACTIONS.items()),
            CAMERA,
        ]
    )
