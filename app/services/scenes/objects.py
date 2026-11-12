"""Objects the engine has no model for: the AI designs them from simple shapes, the engine builds them.

When a scene needs a thing that is not in the 3D catalog (a rocket, a dinosaur, a bus stop, a vending
machine...), the director names it; here the AI turns that name into a small low-poly model made of boxes,
spheres, cylinders and cones. Bad numbers are clamped, so a poor design can look plain but never breaks
the render.
"""

from __future__ import annotations

import logging
import re

from app.services.ai.base import AIProvider

log = logging.getLogger(__name__)

SHAPES = ("box", "sphere", "cylinder", "cone")
MAX_PARTS = 40
OBJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "height": {"type": "number"},
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "shape": {"type": "string", "enum": list(SHAPES)},
                    "size": {"type": "array", "items": {"type": "number"}},
                    "at": {"type": "array", "items": {"type": "number"}},
                    "rotation": {"type": "array", "items": {"type": "number"}},
                    "color": {"type": "string"},
                    "glow": {"type": "number"},
                },
                "required": ["shape", "size", "at", "color"],
            },
        },
    },
    "required": ["height", "parts"],
}

SYSTEM_PROMPT = f"""You are a 3D modeller for a stylised, low-poly animation (like a clean toy world).
Build the object you are given from 6 to {MAX_PARTS} simple parts so that anyone recognises it at a glance:
shape box | sphere | cylinder (vertical axis) | cone (point up), size [x, y, z] in metres (full width, depth,
height of the part), at [x, y, z] = the part's centre, rotation [deg about x, y, z] (optional), color #RRGGBB
(realistic colours), glow (0, or 1-6 for lights, screens, flames).
Axes: z up, the object stands on the ground at z = 0, +y is its front, x is its width. Use its real size
(height = its real height in metres). Get the silhouette and the 2-3 features that make it recognisable right
(a rocket: tall body, nose cone, fins, a window; a dinosaur: body, long neck, head, tail, four legs)."""

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _vec(value, default, low, high) -> list[float]:
    out = []
    for i in range(3):
        try:
            v = float(value[i])
        except (TypeError, ValueError, IndexError):
            v = default[i]
        out.append(round(min(high, max(low, v)), 3))
    return out


def clean_design(data: dict) -> dict | None:
    """Clamp an AI design to what the engine accepts; None when nothing usable is left."""
    try:
        height = float(data.get("height", 1.0))
    except (TypeError, ValueError):
        height = 1.0
    height = round(min(60.0, max(0.05, height)), 3)
    parts = []
    for part in (data.get("parts") or [])[:MAX_PARTS]:
        if not isinstance(part, dict):
            continue
        shape = part.get("shape") if part.get("shape") in SHAPES else "box"
        color = str(part.get("color") or "")
        try:
            glow = min(6.0, max(0.0, float(part.get("glow") or 0)))
        except (TypeError, ValueError):
            glow = 0.0
        parts.append(
            {
                "shape": shape,
                "size": _vec(part.get("size"), (0.3, 0.3, 0.3), 0.005, 200.0),
                "at": _vec(part.get("at"), (0.0, 0.0, 0.15), -200.0, 200.0),
                "rotation": _vec(part.get("rotation"), (0.0, 0.0, 0.0), -360.0, 360.0),
                "color": color if HEX.match(color) else "#9a9a9a",
                "glow": glow,
            }
        )
    return {"height": height, "parts": parts} if len(parts) >= 2 else None


# Hand-made models that beat any design from shapes: names that ask for them use them.
LIBRARY = (
    (("t-rex", "t rex", "trex", "tyrannosaur", "dinosaur", "raptor", "allosaur"), {"kind": "trex", "height": 4.5}),
    (
        ("brachiosaur", "sauropod", "long-neck", "long neck", "diplodocus", "brontosaur", "apatosaur"),
        {"kind": "sauropod", "height": 12.0},
    ),
)


RED, WHITE, STEEL, DARK = "#c4161c", "#f2f2f2", "#b8bcc2", "#2b2d33"
# Small things your hand works (hand_action), built by hand from shapes: base at z=0, front = +y.
HAND_THINGS = (
    (
        ("fire alarm", "fire-alarm"),
        {
            "height": 0.34,
            "parts": [
                {"shape": "box", "size": [0.26, 0.08, 0.34], "at": [0, 0, 0.17], "color": RED},
                {"shape": "box", "size": [0.2, 0.02, 0.07], "at": [0, 0.045, 0.27], "color": WHITE},
                {"shape": "box", "size": [0.14, 0.07, 0.05], "at": [0, 0.07, 0.14], "color": WHITE},
                {"shape": "box", "size": [0.16, 0.02, 0.04], "at": [0, 0.045, 0.06], "color": WHITE},
            ],
        },
    ),
    (
        ("button",),
        {
            "height": 0.32,
            "parts": [
                {"shape": "box", "size": [0.32, 0.08, 0.32], "at": [0, 0, 0.16], "color": "#ffd23f"},
                {
                    "shape": "cylinder",
                    "size": [0.2, 0.2, 0.08],
                    "at": [0, 0.07, 0.16],
                    "rotation": [90, 0, 0],
                    "color": DARK,
                },
                {"shape": "sphere", "size": [0.17, 0.12, 0.17], "at": [0, 0.12, 0.16], "color": RED, "glow": 1.5},
            ],
        },
    ),
    (
        ("tap", "faucet", "sink"),
        {
            "height": 0.35,
            "parts": [
                {"shape": "box", "size": [0.5, 0.35, 0.06], "at": [0, 0.15, 0.03], "color": WHITE},
                {"shape": "cylinder", "size": [0.05, 0.05, 0.3], "at": [0, 0.0, 0.18], "color": STEEL},
                {
                    "shape": "cylinder",
                    "size": [0.045, 0.045, 0.22],
                    "at": [0, 0.1, 0.32],
                    "rotation": [90, 0, 0],
                    "color": STEEL,
                },
                {"shape": "cylinder", "size": [0.04, 0.04, 0.08], "at": [0, 0.2, 0.28], "color": STEEL},
                {"shape": "box", "size": [0.16, 0.03, 0.03], "at": [0, 0.0, 0.34], "color": STEEL},
            ],
        },
    ),
    (
        ("lever", "switch", "breaker"),
        {
            "height": 0.5,
            "parts": [
                {"shape": "box", "size": [0.3, 0.1, 0.4], "at": [0, 0, 0.2], "color": "#5c6066"},
                {
                    "shape": "cylinder",
                    "size": [0.04, 0.04, 0.3],
                    "at": [0, 0.12, 0.33],
                    "rotation": [-35, 0, 0],
                    "color": STEEL,
                },
                {"shape": "sphere", "size": [0.08, 0.08, 0.08], "at": [0, 0.2, 0.46], "color": RED},
            ],
        },
    ),
)


# Things that lie on a table in a 'reaction' scene (what the line is about), hand-built.
CROISSANT = [
    {"shape": "cylinder", "size": [0.34, 0.34, 0.02], "at": [0, 0, 0.01], "color": "#f4f1ea"},
    {"shape": "sphere", "size": [0.075, 0.075, 0.06], "at": [-0.097, -0.034, 0.05], "color": "#c47a2c"},
    {"shape": "sphere", "size": [0.095, 0.095, 0.076], "at": [-0.077, 0.004, 0.05], "color": "#e8a64a"},
    {"shape": "sphere", "size": [0.11, 0.11, 0.088], "at": [-0.042, 0.031, 0.05], "color": "#c47a2c"},
    {"shape": "sphere", "size": [0.11, 0.11, 0.088], "at": [0.0, 0.04, 0.05], "color": "#e8a64a"},
    {"shape": "sphere", "size": [0.11, 0.11, 0.088], "at": [0.042, 0.031, 0.05], "color": "#c47a2c"},
    {"shape": "sphere", "size": [0.095, 0.095, 0.076], "at": [0.077, 0.004, 0.05], "color": "#e8a64a"},
    {"shape": "sphere", "size": [0.075, 0.075, 0.06], "at": [0.097, -0.034, 0.05], "color": "#c47a2c"},
]
TABLE_THINGS = (
    (("croissant", "pastry", "bread"), {"height": 0.09, "parts": CROISSANT}),
    (
        ("empty glass", "glass of water", "glass", "cup"),
        {
            "height": 0.14,
            "parts": [
                {"shape": "cylinder", "size": [0.08, 0.08, 0.13], "at": [0, 0, 0.065], "color": "#cfe6f2"},
                {"shape": "cylinder", "size": [0.085, 0.085, 0.01], "at": [0, 0, 0.005], "color": "#9cc3d8"},
            ],
        },
    ),
    (
        ("bottle",),
        {
            "height": 0.3,
            "parts": [
                {"shape": "cylinder", "size": [0.08, 0.08, 0.22], "at": [0, 0, 0.11], "color": "#7fb8d9"},
                {"shape": "cone", "size": [0.08, 0.08, 0.05], "at": [0, 0, 0.245], "color": "#7fb8d9"},
                {"shape": "cylinder", "size": [0.03, 0.03, 0.04], "at": [0, 0, 0.29], "color": "#1f5fa8"},
                {"shape": "cylinder", "size": [0.082, 0.082, 0.07], "at": [0, 0, 0.12], "color": "#f2f2f2"},
            ],
        },
    ),
    (
        ("letter", "envelope", "note", "paper"),
        {
            "height": 0.03,
            "parts": [
                {"shape": "box", "size": [0.24, 0.16, 0.01], "at": [0, 0, 0.005], "color": "#f4efe2"},
                {"shape": "box", "size": [0.05, 0.04, 0.012], "at": [0.08, 0.04, 0.006], "color": "#c4161c"},
            ],
        },
    ),
    (
        ("pill", "medicine"),
        {
            "height": 0.1,
            "parts": [
                {"shape": "cylinder", "size": [0.07, 0.07, 0.09], "at": [0, 0, 0.045], "color": "#e67e22"},
                {"shape": "cylinder", "size": [0.075, 0.075, 0.025], "at": [0, 0, 0.1], "color": "#f2f2f2"},
                {"shape": "sphere", "size": [0.03, 0.015, 0.015], "at": [0.08, 0.02, 0.008], "color": "#f2f2f2"},
            ],
        },
    ),
)


def library_model(name: str) -> dict | None:
    low = name.lower()
    for words, model in LIBRARY:
        if any(w in low for w in words):
            return {"name": name, "library": "dinosaur", **model}
    for words, design in (*TABLE_THINGS, *HAND_THINGS):
        if any(w in low for w in words):
            return {"name": name, **design}
    return None


def design_object(provider: AIProvider, name: str) -> dict | None:
    """A shape design for `name`, or None if the AI fails (the scene then simply goes without it)."""
    known = library_model(name)
    if known is not None:
        return known
    try:
        result = provider.generate_json(system=SYSTEM_PROMPT, prompt=f"Object: {name}", schema=OBJECT_SCHEMA)
    except Exception as exc:  # noqa: BLE001 - an object is a bonus; the video must not fail for it
        log.warning("Could not design the object %r: %s", name, exc)
        return None
    design = clean_design(result.data if isinstance(result.data, dict) else {})
    if design is not None:
        design["name"] = name
    return design
