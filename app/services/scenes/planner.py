"""Storyboard: turns each script scene into a scene spec for the procedural 3D engine.

The AI can only use what render_engines/core/catalog.py lists, and every spec is
validated by the engine's own validator before it is stored.
"""

from __future__ import annotations

import json
import re

from app.content.profile import CHANNEL_CONCEPT, HUMAN_IMPACT_RULES, VISUAL_STYLE, scale_problems
from app.core.errors import ProviderError
from app.services.ai.base import AIProvider
from render_engines.core.catalog import ACTIONS, ENVIRONMENT_SCALES, ENVIRONMENTS, PROPS, catalog_text
from render_engines.core.spec import SpecError, validate_spec

PROMPT_VERSION = "storyboard-v2"
FPS = 24

_XY = {"type": "array", "items": {"type": "number"}}
_NUMBER = {"type": "number"}
_STRING = {"type": "string"}

SCENE_SCHEMA = {
    "type": "object",
    "properties": {
        "environment": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": list(ENVIRONMENTS)},
                "time_of_day": {"type": "string", "enum": ["dawn", "day", "golden", "dusk", "night"]},
                "room": {
                    "type": "string",
                    "enum": ["living_room", "kitchen", "bedroom", "office", "classroom", "cafe"],
                },
                "style": {"type": "string", "enum": ["old_town", "modern", "suburb", "mixed", "new_york"]},
                "physics": {"type": "boolean"},
                "pedestrians": {"type": "integer"},
                "parked_cars": {"type": "integer"},
                "zombies": {"type": "integer"},
                "crowd": {"type": "integer"},
                "panic": {"type": "integer"},
                "onlookers": {"type": "integer"},
                "audience_fill": _NUMBER,
                "trees": {"type": "integer"},
                "rocks": {"type": "integer"},
                "flowers": {"type": "integer"},
                "fireflies": {"type": "integer"},
                "hill_height": _NUMBER,
                "sun_azimuth": _NUMBER,
                "sun_elevation": _NUMBER,
                "stars": _NUMBER,
            },
            "required": ["type"],
            "additionalProperties": False,
        },
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": _STRING,
                    "start": _XY,
                    "facing": _NUMBER,
                    "scale": _NUMBER,
                    "zombie": {"type": "boolean"},
                    "hat": {"type": "boolean"},
                    "elevation": _NUMBER,
                },
                "required": ["id", "start"],
                "additionalProperties": False,
            },
        },
        "props": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": _STRING,
                    "type": {"type": "string", "enum": list(PROPS)},
                    "location": _XY,
                    "facing": _NUMBER,
                    "radius": _NUMBER,
                    "kind": {"type": "string", "enum": ["earth", "moon", "mars", "sun"]},
                    "spin_rate": _NUMBER,
                    "tilt": _NUMBER,
                },
                "required": ["id", "type", "location"],
                "additionalProperties": False,
            },
        },
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(ACTIONS)},
                    "character": _STRING,
                    "prop": _STRING,
                    "target": _STRING,
                    "towards": _STRING,
                    "side": {"type": "string", "enum": ["left", "right"]},
                    "from": _XY,
                    "to": _XY,
                    "start": _NUMBER,
                    "end": _NUMBER,
                    "at": _NUMBER,
                    "pace": _NUMBER,
                    "to_scale": _NUMBER,
                    "factor": _NUMBER,
                    "rate_from": _NUMBER,
                    "rate_to": _NUMBER,
                    "hold": _NUMBER,
                    "height": _NUMBER,
                    "facing": _NUMBER,
                    "location": _XY,
                    "surface": {"type": "string", "enum": ["wall", "floor"]},
                    "size": _NUMBER,
                    "length": _NUMBER,
                    "x": _NUMBER,
                    "direction_deg": _NUMBER,
                    "accel": _NUMBER,
                    "speed": _NUMBER,
                    "lift": _NUMBER,
                },
                "required": ["type"],
                "additionalProperties": False,
            },
        },
        "camera": {
            "type": "object",
            "properties": {
                "fstop": _NUMBER,
                "handheld": _NUMBER,
                "pov": {"type": "boolean"},
                "pov_item": {"type": "string", "enum": ["none", "phone", "flashlight", "cup"]},
                "pov_sips": {"type": "array", "items": _NUMBER},
                "pov_run": {"type": "boolean"},
                "pov_pushes": {"type": "array", "items": _NUMBER},
                "shots": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "time": _NUMBER,
                            "location": _XY,
                            "target": _STRING,
                            "target_point": _XY,
                            "lens": _NUMBER,
                        },
                        "required": ["time", "location", "lens"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["shots"],
            "additionalProperties": False,
        },
    },
    "required": ["environment", "characters", "props", "actions", "camera"],
    "additionalProperties": False,
}

STORYBOARD_SCHEMA = {
    "type": "object",
    "properties": {"scenes": {"type": "array", "items": SCENE_SCHEMA}},
    "required": ["scenes"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = f"""You are the 3D director of a YouTube channel. {CHANNEL_CONCEPT}
Every video is made only with a procedural 3D engine (no photos, no AI images). Style: {VISUAL_STYLE}

You turn each scene of a script into one engine scene. Use ONLY what the engine supports:
{catalog_text()}

{HUMAN_IMPACT_RULES}

Rules:
- Respect each script scene's 'scale': human-scale scenes happen among people and buildings, at eye level;
  only 'global' scenes may use space and planets.
- One output scene per script scene, in the same order; each lasts exactly the given duration and all times
  are within it.
- Every scene must SHOW what its narration says, as a visible event that starts in the first second of the
  scene: fire when it says fire, a crack when it says something cracks, water rising for floods, glass breaking
  (shatter_windows, physics true), things flying (inertia_shock or fling, physics true), a building falling
  (collapse), people reacting (cover, fall, look_at, walk away). A scene where nothing moves is a failure.
- Choose the place the narration describes (the kitchen, a bedroom, an office, a classroom, an old town
  street, a modern avenue, a suburb) and vary places, camera heights and lenses between scenes.
- Show the idea of the narration with what exists (scale comparisons with trees and people, planets spinning,
  characters walking, growing, jumping, reacting). Prefer one clear action per scene.
- Keep continuity: reuse the same character ids and the same environment type across scenes unless the story
  changes location. Units are metres; a person is 1.7 m tall; keep the camera 3-25 m from the subject
  (for planets, 2.5-6 radii away).
- Keep every scene compact: at most 3 characters, 5 props, 4 actions and 3 camera shots; coordinates are
  [x, y] or [x, y, z]. Never repeat items.
- Each scene needs at least one camera shot at time 0 and one near the end; use smooth moves (push-in, orbit,
  pull-back) that fit the beat (faster for the hook and climax)."""


def _scene_list(scenes: list[dict], durations: list[float]) -> str:
    return "\n".join(
        f"{i}. [{s['beat']}] [{s.get('scale', 'street')}] {durations[i]:.1f}s - narration: {s['narration']!r} - "
        f"shows: {s.get('consequence', '')} (to: {s.get('human_subject', '')}) - shot idea: {s['visual']}"
        for i, s in enumerate(scenes)
    )


def environment_scale_problem(spec: dict, scale: str) -> str | None:
    env = spec.get("environment", {}).get("type", "meadow")
    allowed = ENVIRONMENT_SCALES.get(env, ())
    if scale not in allowed:
        return f"environment '{env}' cannot show a '{scale}' scene (allowed: {list(allowed)})"
    return None


_POINT = re.compile(r"^\s*[\[(]?\s*-?\d+(\.\d+)?(\s*,\s*-?\d+(\.\d+)?){1,2}\s*[\])]?\s*$")


def _as_point(value) -> list[float] | None:
    """'[0, 3, 1]' or '0,3,1' -> [0.0, 3.0, 1.0]; anything else -> None."""
    if not isinstance(value, str) or not _POINT.match(value):
        return None
    numbers = [float(n) for n in json.loads("[" + value.strip().strip("[]()") + "]")]
    return (numbers + [0.0])[:3] if len(numbers) == 2 else numbers


def repair_references(spec: dict) -> None:
    """Fix the reference mistakes the AI makes most often, so one slip does not reject a whole storyboard.

    - an id with different case or spacing ('Car 1' for 'car_1') is mapped to the real id;
    - a camera target written as text ('[0, 3, 1]') becomes a point;
    - an action pointing at a coordinate instead of an id is dropped (actions need a real object).
    Unknown names that are not coordinates are left alone: the validator reports them.
    """
    ids = [item.get("id") for key in ("characters", "props") for item in spec.get(key, [])]
    by_key = {re.sub(r"[\s_-]+", "", str(i).lower()): i for i in ids if isinstance(i, str)}
    known = set(ids) | {"camera"}

    def fix(value):
        if not isinstance(value, str) or value in known:
            return value
        return by_key.get(re.sub(r"[\s_-]+", "", value.lower()), value)

    for shot in spec.get("camera", {}).get("shots", []):
        target = fix(shot.get("target"))
        point = _as_point(target)
        shot["target"] = point if point else target
        if isinstance(shot["target"], str) and shot["target"] not in known:
            shot["target"] = [0, 0, 1]
    kept = []
    for action in spec.get("actions", []):
        broken = False
        for ref in ("character", "prop", "target", "towards"):
            if ref in action:
                action[ref] = fix(action[ref])
                if action[ref] not in known and _as_point(action[ref]) is not None:
                    broken = True
        if not broken:
            kept.append(action)
    spec["actions"] = kept


def finalize(raw: dict, *, duration: float, seed: int, palette: dict | None) -> dict:
    """Engine spec from one planned scene: fixed fields, palette continuity, camera targets."""
    spec = {
        "engine": "cinematic",
        "duration_seconds": round(duration, 3),
        "fps": FPS,
        "seed": seed,
        "environment": raw["environment"],
        "characters": raw.get("characters", []),
        "props": raw.get("props", []),
        "actions": raw.get("actions", []),
        "camera": raw["camera"],
        "captions": [],  # subtitles are burned in at the final edit, timed to the voice
    }
    for character in spec["characters"]:
        character["start"] = list(character["start"][:2])
        if palette:
            character.setdefault("palette", palette)
    for prop in spec["props"]:
        location = list(prop["location"]) + [0.0] * (3 - len(prop["location"]))
        prop["location"] = location[:3]
    for shot in spec["camera"]["shots"]:
        point = shot.pop("target_point", None)
        if "target" not in shot and point:
            shot["target"] = list(point[:3])
        shot["time"] = max(0.0, min(duration, shot["time"]))
        shot.setdefault("target", [0, 0, 1])
    spec["camera"]["shots"].sort(key=lambda shot: shot["time"])
    repair_references(spec)
    for action in spec["actions"]:
        for key in ("start", "end", "at"):
            if key in action:
                action[key] = max(0.0, min(duration, action[key]))
    return spec


def plan_scenes(
    provider: AIProvider,
    *,
    scenes: list[dict],
    durations: list[float],
    visual_bible: dict | None,
    seed: int,
    palette: dict | None = None,
    variety_note: str | None = None,
) -> list[dict]:
    if len(scenes) != len(durations):
        raise ValueError("One duration per scene is required.")
    bible = visual_bible or {}
    prompt = (
        f"Visual continuity notes: {bible}\n\nScript scenes (index, beat, duration, narration, shot idea):\n"
        f"{_scene_list(scenes, durations)}"
    )
    if variety_note:
        prompt += f"\n\n{variety_note}"
    problems: list[str] = []
    for _attempt in range(2):  # one retry, telling the AI exactly what was wrong
        ask = prompt
        if problems:
            ask += (
                "\n\nYour previous storyboard was rejected for these reasons; fix them and keep everything else:\n- "
                + "\n- ".join(problems)
            )
        try:
            result = provider.generate_json(system=SYSTEM_PROMPT, prompt=ask, schema=STORYBOARD_SCHEMA)
        except ProviderError as exc:
            if "truncated" not in str(exc):
                raise
            problems = [
                "Your previous answer was far too long and was cut off. Be compact: at most 3 actions and 3 "
                "camera shots per scene, only the fields you need, no repeated items."
            ]
            continue
        specs, problems = _check(result.data.get("scenes", []), scenes, durations, seed, palette)
        if not problems:
            return specs
    raise ProviderError("Storyboard rejected: " + "; ".join(problems))


def _check(planned, scenes, durations, seed, palette) -> tuple[list[dict], list[str]]:
    if len(planned) != len(scenes):
        return [], [f"Storyboard has {len(planned)} scenes; the script has {len(scenes)}."]
    specs, problems = [], []
    for index, (raw, duration) in enumerate(zip(planned, durations, strict=True)):
        try:
            spec = finalize(raw, duration=duration, seed=seed, palette=palette)
            spec["scale"] = scenes[index].get("scale", "street")
            specs.append(validate_spec(spec))
            mismatch = environment_scale_problem(spec, spec["scale"])
            if mismatch:
                problems.append(f"scene {index}: {mismatch}")
        except (SpecError, KeyError, TypeError, IndexError) as exc:
            problems.append(f"scene {index}: {exc}")
    problems += scale_problems([(s.get("scale", "street"), d) for s, d in zip(scenes, durations, strict=True)])
    return specs, problems
