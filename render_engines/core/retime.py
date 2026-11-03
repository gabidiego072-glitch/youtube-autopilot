"""Stretch or shrink a scene spec to a new duration (e.g. the length of its voice-over). Pure Python."""

from __future__ import annotations

import copy

TIME_KEYS = ("start", "end", "at", "time")


def retime(spec: dict, duration_seconds: float) -> dict:
    old = float(spec["duration_seconds"])
    factor = duration_seconds / old if old else 1.0
    out = copy.deepcopy(spec)
    out["duration_seconds"] = round(duration_seconds, 3)
    for action in out.get("actions", []):
        for key in TIME_KEYS:
            if key in action:
                action[key] = round(action[key] * factor, 3)
    for shot in out.get("camera", {}).get("shots", []):
        shot["time"] = round(shot["time"] * factor, 3)
    for caption in out.get("captions", []):
        caption["start"] = round(caption["start"] * factor, 3)
        caption["end"] = round(min(caption["end"] * factor, duration_seconds), 3)
    return out
