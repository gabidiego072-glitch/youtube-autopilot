"""Voice-over, procedural 3D scenes and final edit for a project's latest script.

Order: voice -> scenes/plan -> scenes/render -> assemble. Scene rendering runs as a
background job (RenderJob) because Blender takes minutes; the other steps are synchronous.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.api.deps import (
    AIProviderDep,
    BlenderDep,
    DbSession,
    FFmpegDep,
    SessionFactoryDep,
    SettingsDep,
    TTSDep,
)
from app.api.lookups import get_project_or_404
from app.core.errors import AutopilotError
from app.db.base import utcnow
from app.models import MediaAsset, RenderJob, Script, VideoProject
from app.models.enums import AssetKind, JobStatus, ProjectStatus, VideoFormat
from app.schemas.content import AssembleRequest, AssetRead, SceneRenderRequest
from app.schemas.project import ScriptRead
from app.schemas.render import RenderJobRead
from app.services.audio.synth import generate_music
from app.services.editing.assembler import EditScene, assemble_video, plan_timeline
from app.services.production.modes import get_mode
from app.services.production.pipeline import transition
from app.services.production.short import output_format, scene_effects, timed_spec
from app.services.rendering.blender import Blender
from app.services.rendering.ffmpeg import FFmpeg
from app.services.rendering.scene3d import render_scene_video
from app.services.scenes.planner import plan_scenes
from render_engines.core.spec import build_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects/{project_id}", tags=["media"])


def _project_dir(settings, project_id: uuid.UUID) -> Path:
    return Path(settings.media_root) / "projects" / str(project_id)


def _latest_script(project) -> Script:
    if not project.scripts:
        raise HTTPException(status_code=409, detail="Generate a script first.")
    return project.scripts[-1]


def _asset(
    project, script, kind: AssetKind, path: Path, scene_index: int | None, provider: str | None, mime: str
) -> MediaAsset:
    return MediaAsset(
        project_id=project.id,
        script_id=script.id,
        kind=kind,
        uri=str(path),
        mime_type=mime,
        size_bytes=path.stat().st_size,
        scene_index=scene_index,
        provider=provider,
    )


def _latest_assets(project, script, kind: AssetKind) -> dict[int, MediaAsset]:
    found = {}
    for asset in project.assets:
        if asset.kind == kind and asset.script_id == script.id and asset.scene_index is not None:
            found[asset.scene_index] = asset
    return found


def _aspect(project) -> str:
    return "9:16" if project.format == VideoFormat.SHORT else "16:9"


@router.post("/voice/generate", response_model=list[AssetRead], status_code=status.HTTP_201_CREATED)
def generate_voice(project_id: uuid.UUID, db: DbSession, settings: SettingsDep, tts: TTSDep) -> list[MediaAsset]:
    """Voice-over per scene with the free local Piper TTS. Scene lengths follow the voice."""
    project = get_project_or_404(db, project_id)
    script = _latest_script(project)
    out_dir = _project_dir(settings, project.id) / f"script_{script.version}" / "voice"
    created = []
    for index, scene in enumerate(script.scenes):
        wav = tts.synthesize(scene["narration"], out_dir / f"scene_{index:03d}.wav")
        created.append(_asset(project, script, AssetKind.VOICEOVER, wav, index, tts.name, "audio/wav"))
    db.add_all(created)
    db.commit()
    return created


@router.post("/scenes/plan", response_model=ScriptRead)
def plan(project_id: uuid.UUID, db: DbSession, ffmpeg: FFmpegDep, ai: AIProviderDep) -> Script:
    """Storyboard: one procedural 3D scene spec per script scene, timed to the voice-over."""
    project = get_project_or_404(db, project_id)
    script = _latest_script(project)
    voices = _latest_assets(project, script, AssetKind.VOICEOVER)
    missing = [i for i in range(len(script.scenes)) if i not in voices]
    if missing:
        raise HTTPException(status_code=409, detail=f"Generate the voice first (missing scenes {missing}).")
    durations = [max(1.0, ffmpeg.probe(Path(voices[i].uri)).duration_seconds + 0.25) for i in range(len(voices))]
    script.scene_specs = plan_scenes(
        ai,
        scenes=script.scenes,
        durations=durations,
        visual_bible=script.visual_bible,
        seed=int(project.id.int % 100_000),
    )
    db.commit()
    db.refresh(script)
    return script


def _timeline(project, script, ffmpeg: FFmpeg):
    """Voice files, their lengths and the scene slots (the same timeline the CLI uses)."""
    voices = _latest_assets(project, script, AssetKind.VOICEOVER)
    missing = [i for i in range(len(script.scenes)) if i not in voices]
    if missing:
        raise HTTPException(status_code=409, detail=f"Generate the voice first (missing scenes {missing}).")
    speech = [ffmpeg.probe(Path(voices[i].uri)).duration_seconds for i in range(len(script.scenes))]
    specs = script.scene_specs or [{} for _ in speech]
    return voices, speech, plan_timeline(speech, [spec.get("transition", "fade") for spec in specs], fps=24)


def _render_scenes_job(
    job_id: uuid.UUID,
    session_factory,
    blender: Blender,
    ffmpeg: FFmpeg,
    out_dir: Path,
    mode_name: str,
    scale: float | None,
    samples: int | None,
    threads: int,
) -> None:
    """Background job: Blender renders every scene, retimed to its voice slot, to a silent clip."""
    with session_factory() as db:
        job = db.get(RenderJob, job_id)
        project = db.get(VideoProject, job.project_id)
        script = db.get(Script, job.script_id)
        job.status, job.started_at = JobStatus.RUNNING, utcnow()
        db.commit()
        try:
            _, _, slots = _timeline(project, script, ffmpeg)
            mode = get_mode(mode_name)
            created = []
            for index, planned in enumerate(script.scene_specs):
                spec = timed_spec(planned, slots[index], planned.get("seed", 0), mode_name)
                spec_path = out_dir / f"scene_{index:03d}.json"
                spec_path.parent.mkdir(parents=True, exist_ok=True)
                spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
                result = render_scene_video(
                    spec_path,
                    out_dir / f"scene_{index:03d}.mp4",
                    blender=blender,
                    ffmpeg=ffmpeg,
                    aspect=_aspect(project),
                    quality=mode.quality,
                    scale=scale,
                    samples=samples,
                    threads=threads,
                    subtitles=False,
                    work_dir=out_dir / f"scene_{index:03d}",
                    motion_blur=spec["motion_blur"],
                )
                created.append(
                    _asset(project, script, AssetKind.VIDEO_CLIP, result.video_path, index, "blender", "video/mp4")
                )
            db.add_all(created)
            job.status, job.output_path = JobStatus.SUCCEEDED, str(out_dir)
        except (AutopilotError, HTTPException) as exc:
            job.status, job.error = JobStatus.FAILED, getattr(exc, "message", None) or str(exc.detail)
        except Exception as exc:  # noqa: BLE001 - a background job must always record its outcome
            logger.exception("scene render job %s failed", job_id)
            job.status, job.error = JobStatus.FAILED, f"Unexpected error: {exc}"
        job.finished_at = utcnow()
        db.commit()


@router.post("/scenes/render", response_model=RenderJobRead, status_code=status.HTTP_202_ACCEPTED)
def render_scenes(
    project_id: uuid.UUID,
    payload: SceneRenderRequest,
    background: BackgroundTasks,
    db: DbSession,
    settings: SettingsDep,
    blender: BlenderDep,
    ffmpeg: FFmpegDep,
    session_factory: SessionFactoryDep,
) -> RenderJob:
    """Start rendering every planned scene with Blender. Poll GET /renders/{job_id}."""
    project = get_project_or_404(db, project_id)
    script = _latest_script(project)
    if not script.scene_specs:
        raise HTTPException(status_code=409, detail="Plan the scenes first (POST /scenes/plan).")
    if not blender.is_available():
        raise HTTPException(status_code=503, detail="Blender not found (scripts/install_blender.sh or BLENDER_BINARY).")
    mode_name = payload.mode or settings.scene_render_quality
    _timeline(project, script, ffmpeg)  # voice must exist before rendering
    ctx = build_context(script.scene_specs[0], _aspect(project), get_mode(mode_name).quality, scale=payload.scale)
    job = RenderJob(project_id=project.id, script_id=script.id, width=ctx.width, height=ctx.height, fps=ctx.fps)
    db.add(job)
    db.commit()
    out_dir = _project_dir(settings, project.id) / f"script_{script.version}" / f"scenes_{job.id.hex[:8]}"
    background.add_task(
        _render_scenes_job,
        job.id,
        session_factory,
        blender,
        ffmpeg,
        out_dir,
        mode_name,
        payload.scale,
        payload.samples,
        settings.scene_render_threads,
    )
    db.refresh(job)
    return job


@router.get("/assets", response_model=list[AssetRead])
def list_assets(project_id: uuid.UUID, db: DbSession) -> list[MediaAsset]:
    return get_project_or_404(db, project_id).assets


@router.post("/assemble", response_model=RenderJobRead, status_code=status.HTTP_201_CREATED)
def assemble(
    project_id: uuid.UUID, payload: AssembleRequest, db: DbSession, settings: SettingsDep, ffmpeg: FFmpegDep
) -> RenderJob:
    """Edit the final MP4 from the rendered 3D scenes and the voice-over (FFmpeg)."""
    project = get_project_or_404(db, project_id)
    script = _latest_script(project)
    if not script.scene_specs:
        raise HTTPException(status_code=409, detail="Plan and render the scenes first.")
    voices, speech, slots = _timeline(project, script, ffmpeg)
    clips = _latest_assets(project, script, AssetKind.VIDEO_CLIP)
    missing = [i for i in range(len(script.scenes)) if i not in clips]
    if missing:
        raise HTTPException(status_code=409, detail=f"Missing rendered scenes {missing}.")
    music = Path(payload.music_path) if payload.music_path else None
    if music is not None and not music.is_file():
        raise HTTPException(status_code=422, detail="music_path does not exist.")
    mode = get_mode(payload.mode)
    base = _project_dir(settings, project.id) / f"script_{script.version}"
    scenes = [
        EditScene(
            Path(clips[i].uri),
            Path(voices[i].uri),
            scene.get("subtitle") or scene["narration"],
            speech[i],
            slots[i],
            scene_effects(ffmpeg, script.scene_specs[i], slots[i], base / "sfx") if mode.sfx else [],
        )
        for i, scene in enumerate(script.scenes)
    ]
    spec = output_format(project.format.value, mode.output_quality or mode.quality)
    previous = project.status
    transition(project, ProjectStatus.RENDERING)
    job = RenderJob(
        project_id=project.id,
        script_id=script.id,
        width=spec.width,
        height=spec.height,
        fps=spec.fps,
        status=JobStatus.RUNNING,
        started_at=utcnow(),
    )
    db.add(job)
    db.commit()

    work = base / f"edit_{job.id.hex[:8]}"
    output = base / f"{mode.name}_{job.id.hex[:8]}.mp4"
    try:
        if music is None and mode.music:
            total = slots[-1].start + slots[-1].duration
            music = generate_music(ffmpeg, total + 1.0, work / "music.wav")
        assemble_video(
            scenes,
            output,
            spec=spec,
            ffmpeg=ffmpeg,
            work_dir=work,
            music_path=music,
            subtitles=payload.subtitles,
            crf=mode.crf,
            preset=mode.preset,
        )
    except AutopilotError as exc:
        job.status, job.error, job.finished_at = JobStatus.FAILED, exc.message, utcnow()
        project.status = previous
        db.commit()
        raise
    job.status, job.output_path, job.finished_at = JobStatus.SUCCEEDED, str(output), utcnow()
    db.add(_asset(project, script, AssetKind.RENDER_OUTPUT, output, None, "ffmpeg", "video/mp4"))
    transition(project, ProjectStatus.RENDERED)
    db.commit()
    db.refresh(job)
    return job
