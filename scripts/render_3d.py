#!/usr/bin/env python3
"""Render a 3D scene spec to MP4 (Blender for 3D, FFmpeg for encode/audio/subtitles).

Example:
    python scripts/render_3d.py examples/scenes/cinematic_lantern_keeper.json \\
        --aspect 9:16 --quality draft --ambient --output out/lantern_keeper_9x16.mp4
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.services.rendering.blender import Blender  # noqa: E402
from app.services.rendering.ffmpeg import FFmpeg  # noqa: E402
from app.services.rendering.scene3d import render_scene_video  # noqa: E402
from render_engines.core.spec import ASPECTS, QUALITY_PRESETS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec", type=Path, help="scene spec JSON")
    parser.add_argument("--output", "-o", type=Path, help="MP4 path (default: out/<spec>_<aspect>.mp4)")
    parser.add_argument("--aspect", choices=sorted(ASPECTS), default="16:9")
    parser.add_argument("--quality", choices=sorted(QUALITY_PRESETS), default="draft")
    parser.add_argument("--scale", type=float, help="override resolution (fraction of 1080p)")
    parser.add_argument("--samples", type=int, help="override Cycles samples per pixel")
    parser.add_argument("--max-frames", type=int, help="render only the first N frames")
    parser.add_argument("--threads", type=int, default=0, help="Blender CPU threads (0 = all cores)")
    parser.add_argument("--audio", type=Path, help="audio file to mux in")
    parser.add_argument("--ambient", action="store_true", help="add a synthesized ambient soundtrack")
    parser.add_argument("--no-subtitles", action="store_true", help="do not burn in the spec captions")
    parser.add_argument("--reuse-frames", action="store_true", help="skip Blender if all frames already exist")
    args = parser.parse_args()

    settings = get_settings()
    output = args.output or Path("out") / f"{args.spec.stem}_{args.aspect.replace(':', 'x')}.mp4"
    result = render_scene_video(
        args.spec,
        output,
        blender=Blender(settings.blender_binary, settings.blender_timeout_seconds),
        ffmpeg=FFmpeg(settings.ffmpeg_binary, settings.ffprobe_binary),
        aspect=args.aspect,
        quality=args.quality,
        audio_path=args.audio,
        ambient_audio=args.ambient,
        subtitles=not args.no_subtitles,
        scale=args.scale,
        samples=args.samples,
        max_frames=args.max_frames,
        threads=args.threads,
        reuse_frames=args.reuse_frames,
    )
    p = result.probe
    print(
        f"{result.video_path}: {result.engine} {p.width}x{p.height} {p.duration_seconds:.2f}s "
        f"({result.frame_count} frames, audio={'yes' if p.has_audio else 'no'}) "
        f"render {result.render_seconds:.0f}s, encode {result.encode_seconds:.0f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
