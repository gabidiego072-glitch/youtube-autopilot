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
    "default 0), tilt (deg). Earth has oceans, continents, ice caps, clouds and a blue atmosphere glow.",
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
}

CAMERA = (
    "camera.shots: list of {time, location [x,y,z], target (id or [x,y,z]), lens (mm, 18-85)} in ascending time; "
    "the camera moves smoothly between shots and always aims at the target. Optional: fstop, handheld (0-0.05)."
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
