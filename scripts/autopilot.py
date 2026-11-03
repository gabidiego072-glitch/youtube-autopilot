#!/usr/bin/env python3
"""YouTube-Autopilot: run the autonomous production pipeline (made to run unattended, e.g. daily in CI).

    python scripts/autopilot.py preflight
    python scripts/autopilot.py run --channel "Qué Pasaría Si" --format short --mode draft
    python scripts/autopilot.py resume <run_id>
    python scripts/autopilot.py approve <run_id>     # after reviewing the video: approve and continue
    python scripts/autopilot.py status [<run_id>]
    python scripts/autopilot.py render-shard <run_id> --shard 0 --shards 4   # parallel cloud rendering
    python scripts/autopilot.py ai-check             # verify the AI key (Gemini: free) with one tiny call
    python scripts/autopilot.py youtube-check        # verify the OAuth credentials (no upload)
    python scripts/autopilot.py upload-test video.mp4  # PRIVATE test upload (needs YOUTUBE_PUBLISHING_ENABLED)
    python scripts/autopilot.py sync-analytics       # YouTube Analytics -> learning loop
    python scripts/autopilot.py trends               # what the idea generator will see

A run stops at 'approval' unless it was started with --auto-publish AND YOUTUBE_PUBLISHING_ENABLED=true.
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.errors import AutopilotError  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.models import Channel, PipelineRun  # noqa: E402
from app.models.enums import (
    PrivacyStatus,  # noqa: E402
    VideoFormat,  # noqa: E402
)
from app.services.ai.factory import get_ai_provider  # noqa: E402
from app.services.analytics.sync import sync_youtube_metrics  # noqa: E402
from app.services.autopilot.factory import piper_binary, preflight, real_services  # noqa: E402
from app.services.autopilot.runner import approve_run, create_run, run_pipeline  # noqa: E402
from app.services.production.short import render_scene_shard  # noqa: E402
from app.services.rendering.blender import Blender  # noqa: E402
from app.services.rendering.ffmpeg import FFmpeg  # noqa: E402
from app.services.trends.signals import collect_signals  # noqa: E402
from app.services.voice.piper import PiperTTS  # noqa: E402
from app.services.youtube.analytics_api import YouTubeAnalyticsCollector  # noqa: E402
from app.services.youtube.base import UploadRequest  # noqa: E402
from app.services.youtube.data_api import YouTubeDataAPIPublisher  # noqa: E402


def summary(run: PipelineRun) -> dict:
    return {
        "run_id": str(run.id),
        "status": run.status.value,
        "current_step": run.current_step,
        "error": run.error,
        "project_id": str(run.project_id) if run.project_id else None,
        "usage": run.usage,
        "steps": [{k: s.get(k) for k in ("name", "status", "attempts", "error")} for s in run.steps],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    run_p = sub.add_parser("run")
    run_p.add_argument("--channel", required=True, help="channel name (created if missing) or id")
    run_p.add_argument("--niche", default="curiosidades, ciencia y situaciones hipotéticas")
    run_p.add_argument("--format", choices=[f.value for f in VideoFormat], default="short")
    run_p.add_argument("--mode", choices=["preview", "draft", "hd", "final"], default="draft")
    run_p.add_argument("--auto-publish", action="store_true")
    run_p.add_argument("--until", help="stop after this step (e.g. storyboard)")
    resume_p = sub.add_parser("resume")
    resume_p.add_argument("run_id")
    approve_p = sub.add_parser("approve")
    approve_p.add_argument("run_id")
    status_p = sub.add_parser("status")
    status_p.add_argument("run_id", nargs="?")
    shard_p = sub.add_parser("render-shard", help="render a subset of a run's scenes (after --until storyboard)")
    shard_p.add_argument("run_id")
    shard_p.add_argument("--shard", type=int, required=True)
    shard_p.add_argument("--shards", type=int, required=True)
    sub.add_parser("youtube-check")
    sub.add_parser("ai-check")
    upload_p = sub.add_parser("upload-test")
    upload_p.add_argument("video", type=Path)
    upload_p.add_argument("--title", default="Prueba privada YouTube-Autopilot")
    upload_p.add_argument("--thumbnail", type=Path)
    sub.add_parser("sync-analytics")
    sub.add_parser("trends")
    args = parser.parse_args()
    settings = get_settings()

    if args.command in ("youtube-check", "upload-test", "trends"):
        return youtube_command(args, settings)
    if args.command == "ai-check":
        provider = get_ai_provider(settings)
        if hasattr(provider, "list_models"):
            models = provider.list_models()
            print(json.dumps({"provider": provider.name, "available_models": models}, indent=2))
            if settings.gemini_model not in models:
                print(f"GEMINI_MODEL={settings.gemini_model} is not in the list: pick one above.", file=sys.stderr)
                return 1
        result = provider.generate_json(
            system="Answer briefly.",
            prompt="Reply with ok=true.",
            schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
        )
        print(json.dumps({"ok": result.data.get("ok"), "model": result.model, "usage": result.usage}, indent=2))
        return 0

    if args.command == "preflight":
        problems = preflight(settings)
        print(json.dumps({"ready": not problems, "problems": problems}, ensure_ascii=False, indent=2))
        return 0 if not problems else 1

    with get_session_factory()() as db:
        if args.command == "status":
            runs = (
                [db.get(PipelineRun, uuid.UUID(args.run_id))]
                if args.run_id
                else list(db.scalars(select(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(10)))
            )
            print(json.dumps([summary(r) for r in runs if r], ensure_ascii=False, indent=2, default=str))
            return 0
        if args.command == "sync-analytics":
            print(json.dumps(sync_youtube_metrics(db, YouTubeAnalyticsCollector(settings)), indent=2))
            return 0
        if args.command == "render-shard":
            return render_shard(db, args, settings)
        problems = preflight(settings)
        if problems:
            print(json.dumps({"ready": False, "problems": problems}, ensure_ascii=False, indent=2))
            return 2
        services = real_services(settings)
        if args.command == "run":
            channel = None
            try:
                channel = db.get(Channel, uuid.UUID(args.channel))
            except ValueError:
                channel = db.scalar(select(Channel).where(Channel.name == args.channel))
            if channel is None:
                channel = Channel(name=args.channel, niche=args.niche, language="es")
                db.add(channel)
                db.commit()
            run = create_run(db, channel, VideoFormat(args.format), args.mode, args.auto_publish)
            run = run_pipeline(db, run, services, until=args.until)
        else:
            run = db.get(PipelineRun, uuid.UUID(args.run_id))
            if args.command == "approve":
                approve_run(db, run)
            run = run_pipeline(db, run, services)
        print(json.dumps(summary(run), ensure_ascii=False, indent=2, default=str))
        return 0 if run.status.value in ("published", "waiting_approval") or args.command == "run" and args.until else 1


def render_shard(db, args, settings) -> int:
    """Render this shard's scenes into the run's work dir; the 'render' step later reuses the clips."""
    run = db.get(PipelineRun, uuid.UUID(args.run_id))
    work = Path(settings.media_root) / "autopilot" / str(run.id)
    production = work / "production.json"
    if not production.is_file():
        print(f"{production} not found: run the pipeline with --until storyboard first.", file=sys.stderr)
        return 2
    report = render_scene_shard(
        production,
        run.render_mode,
        work,
        blender=Blender(settings.blender_binary, settings.blender_timeout_seconds),
        ffmpeg=FFmpeg(settings.ffmpeg_binary, settings.ffprobe_binary),
        tts=PiperTTS(piper_binary(settings), settings.piper_voice_model, settings.piper_length_scale),
        shard=args.shard,
        shards=args.shards,
        threads=settings.scene_render_threads,
    )
    print(json.dumps(report, indent=2))
    return 0


def youtube_command(args, settings) -> int:
    if args.command == "trends":
        signals = collect_signals(settings)
        print(json.dumps(signals.__dict__, ensure_ascii=False, indent=2))
        return 0
    publisher = YouTubeDataAPIPublisher(settings)
    if args.command == "youtube-check":
        channel = publisher.channel()  # refreshes the access token, then reads the channel
        print(
            json.dumps(
                {
                    "ok": True,
                    "channel": channel,
                    "publishing_enabled": settings.youtube_publishing_enabled,
                    "public_allowed": settings.youtube_allow_public,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    # upload-test: always private, whatever the settings say.
    result = publisher.upload(
        UploadRequest(
            video_path=args.video,
            title=args.title,
            description="Subida de prueba automática (privada). YouTube-Autopilot.",
            privacy=PrivacyStatus.PRIVATE,
            thumbnail_path=args.thumbnail,
        )
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    print(f"Revisa el vídeo (privado) en https://studio.youtube.com/video/{result.youtube_video_id}/edit")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AutopilotError as exc:  # clear message, no traceback (and never a secret)
        print(f"error ({exc.code}): {exc.message}", file=sys.stderr)
        sys.exit(3)
