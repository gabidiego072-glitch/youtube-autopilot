#!/usr/bin/env python3
"""Produce a Short from a production file.

    python scripts/produce_short.py productions/what_if_earth_stops/production.json --mode preview --scenes 0,1
    python scripts/produce_short.py productions/what_if_earth_stops/production.json --mode draft
    python scripts/produce_short.py productions/what_if_earth_stops/production.json --mode final

Modes: preview (5-10 s fragment of chosen scenes), draft (whole video, reduced quality),
final (whole video, 1080x1920, every audio layer). Renders resume if interrupted.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.services.production.modes import MODES  # noqa: E402
from app.services.production.short import produce_short  # noqa: E402
from app.services.rendering.blender import Blender  # noqa: E402
from app.services.rendering.ffmpeg import FFmpeg  # noqa: E402
from app.services.voice.piper import PiperTTS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("production", type=Path)
    parser.add_argument("--mode", choices=sorted(MODES), default="draft")
    parser.add_argument("--scenes", help="preview only: comma-separated scene indexes")
    parser.add_argument("--out", type=Path, help="output folder (default: out/<production id>)")
    parser.add_argument("--threads", type=int, default=0)
    args = parser.parse_args()

    settings = get_settings()
    production_id = json.loads(args.production.read_text(encoding="utf-8")).get("id", args.production.stem)
    piper = settings.piper_binary
    venv_piper = Path(sys.executable).parent / "piper"
    if piper == "piper" and venv_piper.is_file():
        piper = str(venv_piper)
    voice = settings.piper_voice_model or Path("models/voices/es_ES-davefx-medium.onnx")
    report = produce_short(
        args.production,
        args.mode,
        args.out or Path("out") / production_id,
        blender=Blender(settings.blender_binary, settings.blender_timeout_seconds),
        ffmpeg=FFmpeg(settings.ffmpeg_binary, settings.ffprobe_binary),
        tts=PiperTTS(piper, voice, settings.piper_length_scale),
        scenes=[int(s) for s in args.scenes.split(",")] if args.scenes else None,
        threads=args.threads,
    )
    print(json.dumps({k: v for k, v in report.items() if k != "timeline"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
