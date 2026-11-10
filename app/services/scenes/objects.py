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


def design_object(provider: AIProvider, name: str) -> dict | None:
    """A shape design for `name`, or None if the AI fails (the scene then simply goes without it)."""
    try:
        result = provider.generate_json(system=SYSTEM_PROMPT, prompt=f"Object: {name}", schema=OBJECT_SCHEMA)
    except Exception as exc:  # noqa: BLE001 - an object is a bonus; the video must not fail for it
        log.warning("Could not design the object %r: %s", name, exc)
        return None
    design = clean_design(result.data if isinstance(result.data, dict) else {})
    if design is not None:
        design["name"] = name
    return design
