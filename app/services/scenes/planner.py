"""Storyboard: turns each script scene into a scene spec for the procedural 3D engine.

The AI can only use what render_engines/core/catalog.py lists, and every spec is
validated by the engine's own validator before it is stored.
"""

from __future__ import annotations

from app.content.profile import CHANNEL_CONCEPT, VISUAL_STYLE
from app.core.errors import ProviderError
from app.services.ai.base import AIProvider
from render_engines.core.catalog import ACTIONS, ENVIRONMENTS, PROPS, catalog_text
from render_engines.core.spec import SpecError, validate_spec

PROMPT_VERSION = "storyboard-v1"
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
                "time_of_day": {"type": "string", "enum": ["dawn", "day", "dusk"]},
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
                "properties": {"id": _STRING, "start": _XY, "facing": _NUMBER, "scale": _NUMBER},
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

Rules:
- One output scene per script scene, in the same order; each lasts exactly the given duration and all times
  are within it.
- Show the idea of the narration with what exists (scale comparisons with trees and people, planets spinning,
  characters walking, growing, jumping, reacting). Prefer one clear action per scene.
- Keep continuity: reuse the same character ids and the same environment type across scenes unless the story
  changes location. Units are metres; a person is 1.7 m tall; keep the camera 3-25 m from the subject
  (for planets, 2.5-6 radii away).
- Each scene needs at least one camera shot at time 0 and one near the end; use smooth moves (push-in, orbit,
  pull-back) that fit the beat (faster for the hook and climax)."""


def _scene_list(scenes: list[dict], durations: list[float]) -> str:
    return "\n".join(
        f"{i}. [{s['beat']}] {durations[i]:.1f}s - narration: {s['narration']!r} - shot idea: {s['visual']}"
        for i, s in enumerate(scenes)
    )


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
) -> list[dict]:
    if len(scenes) != len(durations):
        raise ValueError("One duration per scene is required.")
    bible = visual_bible or {}
    prompt = (
        f"Visual continuity notes: {bible}\n\nScript scenes (index, beat, duration, narration, shot idea):\n"
        f"{_scene_list(scenes, durations)}"
    )
    result = provider.generate_json(system=SYSTEM_PROMPT, prompt=prompt, schema=STORYBOARD_SCHEMA)
    planned = result.data.get("scenes", [])
    if len(planned) != len(scenes):
        raise ProviderError(f"Storyboard has {len(planned)} scenes; the script has {len(scenes)}.")
    specs, problems = [], []
    for index, (raw, duration) in enumerate(zip(planned, durations, strict=True)):
        try:
            spec = finalize(raw, duration=duration, seed=seed, palette=palette)
            specs.append(validate_spec(spec))
        except (SpecError, KeyError, TypeError, IndexError) as exc:
            problems.append(f"scene {index}: {exc}")
    if problems:
        raise ProviderError("Storyboard rejected: " + "; ".join(problems))
    return specs
