"""Scene spec loading/validation and render presets. Pure Python (no bpy).

A scene spec is a JSON document describing what to build and animate. Times are
in seconds; engines convert them to frames with `RenderContext.frame`.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

ENGINES = ("cinematic",)
ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920)}

# scale = fraction of full 1080p resolution.
QUALITY_PRESETS = {
    "test": {"scale": 0.1, "samples": 1},
    "draft": {"scale": 0.5, "samples": 12},
    "preview": {"scale": 2 / 3, "samples": 24},
    "final": {"scale": 1.0, "samples": 64},
}

MIN_DURATION, MAX_DURATION = 1.0, 60.0


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class RenderContext:
    engine: str
    aspect: str
    width: int
    height: int
    fps: int
    duration_seconds: float
    samples: int
    seed: int
    frame_start: int = 1
    max_frames: int | None = None

    @property
    def portrait(self) -> bool:
        return self.height > self.width

    @property
    def frame_count(self) -> int:
        total = max(1, round(self.duration_seconds * self.fps))
        return min(total, self.max_frames) if self.max_frames else total

    @property
    def frame_end(self) -> int:
        return self.frame_start + self.frame_count - 1

    def frame(self, seconds: float) -> int:
        return self.frame_start + round(seconds * self.fps)


def resolution(aspect: str, quality: str, scale: float | None = None) -> tuple[int, int]:
    if aspect not in ASPECTS:
        raise SpecError(f"Unsupported aspect '{aspect}'. Use one of {sorted(ASPECTS)}.")
    if quality not in QUALITY_PRESETS:
        raise SpecError(f"Unknown quality '{quality}'. Use one of {sorted(QUALITY_PRESETS)}.")
    factor = scale if scale is not None else QUALITY_PRESETS[quality]["scale"]
    w, h = ASPECTS[aspect]
    # H.264 with yuv420p needs even dimensions.
    return (max(2, int(math.floor(w * factor / 2)) * 2), max(2, int(math.floor(h * factor / 2)) * 2))


def validate_spec(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise SpecError("Spec must be a JSON object.")
    engine = spec.get("engine")
    if engine not in ENGINES:
        raise SpecError(f"'engine' must be one of {ENGINES}.")
    duration = spec.get("duration_seconds")
    if not isinstance(duration, (int, float)) or not MIN_DURATION <= duration <= MAX_DURATION:
        raise SpecError(f"'duration_seconds' must be between {MIN_DURATION} and {MAX_DURATION}.")
    fps = spec.get("fps", 24)
    if fps not in (24, 25, 30, 60):
        raise SpecError("'fps' must be 24, 25, 30 or 60.")
    if not isinstance(spec.get("seed", 0), int):
        raise SpecError("'seed' must be an integer.")
    for key in ("characters", "props", "actions", "captions"):
        if not isinstance(spec.get(key, []), list):
            raise SpecError(f"'{key}' must be a list.")
    ids = [item.get("id") for key in ("characters", "props") for item in spec.get(key, [])]
    if any(not isinstance(i, str) or not i for i in ids):
        raise SpecError("Every character and prop needs a string 'id'.")
    if len(ids) != len(set(ids)):
        raise SpecError("Character and prop ids must be unique.")
    known = set(ids) | {"camera"}
    for action in spec.get("actions", []):
        for ref in ("character", "prop", "target"):
            if ref in action and isinstance(action[ref], str) and action[ref] not in known:
                raise SpecError(f"Action references unknown id '{action[ref]}'.")
        start = action.get("start", action.get("at", 0))
        if not 0 <= start <= duration:
            raise SpecError(f"Action '{action.get('type')}' starts outside the video ({start}s).")
    shots = spec.get("camera", {}).get("shots", [])
    if not shots:
        raise SpecError("'camera.shots' needs at least one shot.")
    times = [shot.get("time") for shot in shots]
    if times != sorted(times) or any(not isinstance(t, (int, float)) for t in times):
        raise SpecError("Camera shot times must be numbers in ascending order.")
    for caption in spec.get("captions", []):
        if not caption.get("text") or not 0 <= caption.get("start", -1) < caption.get("end", -1) <= duration:
            raise SpecError("Each caption needs text and 0 <= start < end <= duration.")
    return spec


def load_spec(path: str | Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecError(f"Cannot read spec {path}: {exc}") from exc
    return validate_spec(data)


def build_context(
    spec: dict,
    aspect: str,
    quality: str,
    *,
    scale: float | None = None,
    samples: int | None = None,
    max_frames: int | None = None,
) -> RenderContext:
    width, height = resolution(aspect, quality, scale)
    return RenderContext(
        engine=spec["engine"],
        aspect=aspect,
        width=width,
        height=height,
        fps=spec.get("fps", 24),
        duration_seconds=float(spec["duration_seconds"]),
        samples=samples or QUALITY_PRESETS[quality]["samples"],
        seed=spec.get("seed", 0),
        max_frames=max_frames,
    )
