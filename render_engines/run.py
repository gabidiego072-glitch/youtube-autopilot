"""Blender entry point. Usage:

    blender --background --factory-startup --python render_engines/run.py -- \
        --spec examples/scenes/cinematic_lantern_keeper.json --aspect 16:9 --quality draft \
        --frames-dir out/frames
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bpy  # noqa: E402

from render_engines.core.blender.scene import render_animation, reset_scene  # noqa: E402
from render_engines.core.spec import ASPECTS, QUALITY_PRESETS, build_context, load_spec  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser(prog="render_engines/run.py")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--aspect", choices=sorted(ASPECTS), default="16:9")
    parser.add_argument("--quality", choices=sorted(QUALITY_PRESETS), default="draft")
    parser.add_argument("--frames-dir", required=True)
    parser.add_argument("--scale", type=float, help="override resolution scale (fraction of 1080p)")
    parser.add_argument("--samples", type=int, help="override Cycles samples")
    parser.add_argument("--max-frames", type=int, help="render only the first N frames")
    parser.add_argument("--save-blend", help="also save the built scene as a .blend file")
    parser.add_argument("--threads", type=int, default=0, help="CPU threads (0 = all)")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv)
    spec = load_spec(args.spec)
    ctx = build_context(
        spec, args.aspect, args.quality, scale=args.scale, samples=args.samples, max_frames=args.max_frames
    )
    Path(args.frames_dir).mkdir(parents=True, exist_ok=True)

    scene = reset_scene()
    from render_engines import cinematic as engine

    started = time.time()
    engine.build(spec, ctx, scene, str(Path(args.frames_dir).resolve()))
    if args.threads:
        scene.render.threads_mode = "FIXED"
        scene.render.threads = args.threads
    print(
        f"[autopilot] built {spec['engine']} scene in {time.time() - started:.1f}s: "
        f"{ctx.width}x{ctx.height} {ctx.frame_count} frames @ {ctx.fps}fps, {ctx.samples} samples",
        flush=True,
    )
    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save_blend).resolve()))

    def on_frame(scn, _depsgraph=None):
        print(f"[autopilot] frame {scn.frame_current}/{scn.frame_end} ({time.time() - started:.0f}s)", flush=True)

    bpy.app.handlers.render_post.append(on_frame)
    render_animation()
    print(f"[autopilot] done in {time.time() - started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
