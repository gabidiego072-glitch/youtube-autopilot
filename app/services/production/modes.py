"""The three ways to render a video.

preview  a 5-10 s fragment (chosen scenes) to check scenes, objects, light and animation
draft    the whole video at reduced resolution/quality, with voice, music, effects and subtitles
lite     the whole video at 540p/3 samples, upscaled to 1080p: for slow computers
hd       the whole video at 720p/4 samples, upscaled to 1080p: publishable, ~4x cheaper than final
final    the whole video, publishable: 1080x1920 for Shorts, every audio layer, subtitles burned in
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderMode:
    name: str
    quality: str  # render_engines preset (resolution scale + samples)
    full_video: bool
    max_seconds: float | None  # preview fragments are capped
    motion_blur: bool
    crf: int
    preset: str
    music: bool = True
    sfx: bool = True
    output_quality: str | None = None  # edit at this preset's resolution (upscales a cheaper render)


MODES = {
    "preview": RenderMode(
        "preview", "preview", full_video=False, max_seconds=10.0, motion_blur=False, crf=24, preset="veryfast"
    ),
    "draft": RenderMode("draft", "draft", full_video=True, max_seconds=None, motion_blur=False, crf=22, preset="fast"),
    "lite": RenderMode(
        "lite",
        "lite",
        full_video=True,
        max_seconds=None,
        motion_blur=False,
        crf=19,
        preset="medium",
        output_quality="final",
    ),
    "hd": RenderMode(
        "hd",
        "hd",
        full_video=True,
        max_seconds=None,
        motion_blur=False,
        crf=18,
        preset="medium",
        output_quality="final",
    ),
    "final": RenderMode("final", "final", full_video=True, max_seconds=None, motion_blur=True, crf=18, preset="medium"),
}


def get_mode(name: str) -> RenderMode:
    if name not in MODES:
        raise ValueError(f"Unknown render mode '{name}'. Use one of {sorted(MODES)}.")
    return MODES[name]
