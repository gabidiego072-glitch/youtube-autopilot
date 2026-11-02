"""3D scene -> MP4 pipeline.

Blender (render_engines/) renders PNG frames; FFmpeg only does the final
encode, audio and subtitles.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from app.services.rendering.blender import Blender
from app.services.rendering.ffmpeg import FFmpeg, ProbeResult, write_srt
from render_engines.core.spec import build_context, load_spec


@dataclass(frozen=True)
class Scene3DResult:
    video_path: Path
    frames_dir: Path
    engine: str
    aspect: str
    frame_count: int
    render_seconds: float
    encode_seconds: float
    probe: ProbeResult


def render_scene_video(
    spec_path: Path,
    output_path: Path,
    *,
    blender: Blender,
    ffmpeg: FFmpeg,
    aspect: str = "16:9",
    quality: str = "draft",
    work_dir: Path | None = None,
    audio_path: Path | None = None,
    ambient_audio: bool = False,
    subtitles: bool = True,
    scale: float | None = None,
    samples: int | None = None,
    max_frames: int | None = None,
    threads: int = 0,
    reuse_frames: bool = False,
) -> Scene3DResult:
    spec = load_spec(spec_path)  # validate before spending render time
    ctx = build_context(spec, aspect, quality, scale=scale, samples=samples, max_frames=max_frames)
    work_dir = work_dir or output_path.with_suffix("")
    frames_dir = work_dir / "frames"
    work_dir.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    existing = sorted(frames_dir.glob("frame_*.png")) if frames_dir.exists() else []
    if not (reuse_frames and len(existing) == ctx.frame_count):
        blender.render_frames(
            spec_path.resolve(),
            frames_dir.resolve(),
            log_path=work_dir / "blender.log",
            aspect=aspect,
            quality=quality,
            scale=scale,
            samples=samples,
            max_frames=max_frames,
            threads=threads,
        )
    render_seconds = time.monotonic() - started

    started = time.monotonic()
    duration = ctx.frame_count / ctx.fps
    if audio_path is None and ambient_audio:
        audio_path = ffmpeg.generate_ambient_audio(duration, work_dir / "ambient.wav")
    srt = None
    captions = [c for c in spec.get("captions", []) if c["start"] < duration]
    if subtitles and captions:
        srt = write_srt([{**c, "end": min(c["end"], duration)} for c in captions], work_dir / "captions.srt")
    probe = ffmpeg.encode_frames(
        frames_dir, ctx.fps, output_path, audio_path=audio_path, subtitles_path=srt, portrait=ctx.portrait
    )
    return Scene3DResult(
        video_path=output_path,
        frames_dir=frames_dir,
        engine=spec["engine"],
        aspect=aspect,
        frame_count=ctx.frame_count,
        render_seconds=render_seconds,
        encode_seconds=time.monotonic() - started,
        probe=probe,
    )
