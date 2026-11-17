"""Does each scene SHOW what its narration line says? Checked by looking at it, before the long render.

The recipes guarantee well-made shots, not the right ones: the homeless video showed five empty streets while
the voice talked about keys, hospitals and shelters. Here a couple of small frames of every scene are
rendered in seconds and the AI looks at them next to the line. A scene that does not show its line is
planned again with that feedback. Lines are never rewritten to fit the picture (that broke a story once);
the script prompt keeps them filmable.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

from app.services.ai.base import AIProvider

log = logging.getLogger(__name__)

STILLS = (0.45, 0.9)  # moments of the scene that are looked at
CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "seen": {"type": "string"},
        "shows_it": {"type": "boolean"},
        "missing": {"type": "string"},
    },
    "required": ["seen", "shows_it", "missing"],
}
CHECK_SYSTEM = """You review a first-person 3D animated YouTube Short before it is rendered. You get one narration
line and frames of the scene (or one frame of each of its short sub-scenes, in order) that will play while the
line is spoken (stylised low-poly 3D, the viewer's own hands may be at the bottom). Be strict and literal,
like a viewer who hears the line and looks at the screen.
seen: what the frames actually show, in one sentence (place, people, objects, events, numbers on screen).
shows_it: true if the concrete thing the line is about is on screen: the person, the place, the object or the
event it names (a line about whispering in your flat shows a flat with you there; a line about a bus shows a bus).
Things no camera can film (a sound, a smell, a temperature, a thought, an echo) do not have to be drawn: judge the
place, people and objects around them. A generic street or room unrelated to what the line names is false.
On-screen subtitles and the counter at the top do not count.
missing: if false, what the picture would need to show the line (one short sentence); empty if true."""


def stills_for(blender, spec: dict, folder: Path, seed: int) -> list[Path]:
    """Frames of the scene; a line made of several beats gives one frame of each of its sub-scenes."""
    folder.mkdir(parents=True, exist_ok=True)
    if spec.get("parts"):
        frames = []
        for j, part in enumerate(spec["parts"]):
            frames += _render(blender, part, folder / f"part_{j}", seed, (0.6,))
        return frames
    return _render(blender, spec, folder, seed, STILLS)


def _render(blender, spec: dict, folder: Path, seed: int, moments) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "scene.json"
    body = {k: v for k, v in spec.items() if k not in ("parts", "beats", "shares")}
    path.write_text(
        json.dumps({"engine": "cinematic", "fps": 24, "seed": seed, "motion_blur": False, **body}), encoding="utf-8"
    )
    return blender.render_stills(path, folder, moments)


FLAT_RANGE = 35  # the same thresholds as the video QA (app/services/qa/video.py)
WASHED_AVG, WASHED_SAT = 170, 8.0
FLAT_VERDICT = {
    "seen": "a flat, blank picture (the camera faces a plain wall, panel or empty screen)",
    "shows_it": False,
    "missing": "the camera must not face a plain wall: frame the people, the objects or the street of the line",
}


def flat_still(path: Path, ffmpeg: str = "ffmpeg") -> bool:
    """A preview that is one flat colour or washed out (Nov 17: 5 s of a grey office panel stopped the English
    video at the final QA, after two hours of render). Caught here, the scene is planned again instead."""
    try:
        log = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-i",
                str(path),
                "-vf",
                "crop=iw:ih*0.5:0:ih*0.25,signalstats,metadata=print",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        ).stderr
    except (OSError, subprocess.SubprocessError):
        return False
    values = {k: float(v) for k, v in re.findall(r"signalstats\.(YLOW|YHIGH|YAVG|SATAVG)=([\d.]+)", log)}
    if len(values) < 4:
        return False
    flat = values["YHIGH"] - values["YLOW"] < FLAT_RANGE
    washed = values["YAVG"] >= WASHED_AVG and values["SATAVG"] < WASHED_SAT
    return flat or washed


def check_scene(ai: AIProvider, narration: str, images: list[bytes]) -> dict:
    result = ai.generate_json(
        system=CHECK_SYSTEM, prompt=f"Narration line: {narration}", schema=CHECK_SCHEMA, images=images
    )
    data = result.data if isinstance(result.data, dict) else {}
    return {
        "seen": str(data.get("seen", "")),
        "shows_it": bool(data.get("shows_it", False)),
        "missing": str(data.get("missing", "")),
    }


def check_scenes(
    ai: AIProvider,
    blender,
    specs: list[dict],
    narrations: list[str],
    work: Path,
    seed: int,
    only: list[int] | None = None,
) -> dict[int, dict]:
    """{scene index: verdict} for the scenes looked at; a scene that cannot be rendered or judged is skipped."""
    verdicts = {}
    for i in only if only is not None else range(len(specs)):
        try:
            frames = stills_for(blender, specs[i], work / f"scene_{i:02d}", seed + i)
            if not frames:
                continue
            if any(flat_still(f) for f in frames):  # no need to ask the AI: replan it (and save quota)
                verdicts[i] = dict(FLAT_VERDICT)
                continue
            verdicts[i] = check_scene(ai, narrations[i], [f.read_bytes() for f in frames])
        except Exception as exc:  # noqa: BLE001 - the check helps; it must never stop the day's video
            log.warning("scene %s could not be checked: %s", i, exc)
    return verdicts
