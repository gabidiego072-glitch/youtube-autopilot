#!/usr/bin/env python3
"""YouTube-Autopilot: run the autonomous production pipeline (made to run unattended, e.g. daily in CI).

    python scripts/autopilot.py preflight
    python scripts/autopilot.py run --channel "Qué Pasaría Si" --format short --mode draft
    python scripts/autopilot.py resume <run_id>
    python scripts/autopilot.py approve <run_id>     # after reviewing the video: approve and continue
    python scripts/autopilot.py status [<run_id>]

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
from app.db.session import get_session_factory  # noqa: E402
from app.models import Channel, PipelineRun  # noqa: E402
from app.models.enums import VideoFormat  # noqa: E402
from app.services.autopilot.factory import preflight, real_services  # noqa: E402
from app.services.autopilot.runner import approve_run, create_run, run_pipeline  # noqa: E402


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
    run_p.add_argument("--mode", choices=["preview", "draft", "final"], default="draft")
    run_p.add_argument("--auto-publish", action="store_true")
    run_p.add_argument("--until", help="stop after this step (e.g. storyboard)")
    resume_p = sub.add_parser("resume")
    resume_p.add_argument("run_id")
    approve_p = sub.add_parser("approve")
    approve_p.add_argument("run_id")
    status_p = sub.add_parser("status")
    status_p.add_argument("run_id", nargs="?")
    args = parser.parse_args()
    settings = get_settings()

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


if __name__ == "__main__":
    sys.exit(main())
