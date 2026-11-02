"""Visuals, voice-over and final edit for a project's latest script.

These run synchronously for now; the background worker (roadmap) will move them off the request.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession, FFmpegDep, ImageProviderDep, SettingsDep, TTSDep
from app.api.lookups import get_project_or_404
from app.core.errors import AutopilotError
from app.db.base import utcnow
from app.models import MediaAsset, RenderJob
from app.models.enums import AssetKind, JobStatus, ProjectStatus, VideoFormat
from app.schemas.content import AssembleRequest, AssetRead, VisualsRequest
from app.schemas.render import RenderJobRead
from app.services.editing.assembler import SceneMedia, assemble_video
from app.services.production.formats import get_format_spec, scaled
from app.services.production.pipeline import transition
from app.services.visuals.prompting import build_shot_prompts, project_seed
from app.services.visuals.providers import get_video_provider

router = APIRouter(prefix="/projects/{project_id}", tags=["media"])


def _project_dir(settings, project_id: uuid.UUID) -> Path:
    return Path(settings.media_root) / "projects" / str(project_id)


def _latest_script(project):
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


@router.post("/visuals/generate", response_model=list[AssetRead], status_code=status.HTTP_201_CREATED)
def generate_visuals(
    project_id: uuid.UUID, payload: VisualsRequest, db: DbSession, settings: SettingsDep, images: ImageProviderDep
) -> list[MediaAsset]:
    """One hyper-realistic AI image per scene (consistent subjects + seed), optionally animated."""
    project = get_project_or_404(db, project_id)
    script = _latest_script(project)
    aspect = payload.aspect or ("9:16" if project.format == VideoFormat.SHORT else "16:9")
    shots = build_shot_prompts(script.scenes, script.visual_bible, aspect=aspect, project_id=str(project.id))
    out_dir = _project_dir(settings, project.id) / f"script_{script.version}" / "visuals"
    video = get_video_provider(settings) if payload.animate else None
    created = []
    for shot in shots:
        image = images.generate(shot, out_dir / f"scene_{shot.scene_index:03d}.png")
        created.append(_asset(project, script, AssetKind.IMAGE, image, shot.scene_index, images.name, "image/png"))
        if video is not None:
            seconds = float(script.scenes[shot.scene_index]["duration_seconds"])
            clip = video.animate(
                image,
                shot.prompt,
                seconds,
                out_dir / f"scene_{shot.scene_index:03d}.mp4",
                seed=project_seed(str(project.id)),
            )
            created.append(
                _asset(project, script, AssetKind.VIDEO_CLIP, clip, shot.scene_index, video.name, "video/mp4")
            )
    db.add_all(created)
    db.commit()
    return created


@router.post("/voice/generate", response_model=list[AssetRead], status_code=status.HTTP_201_CREATED)
def generate_voice(project_id: uuid.UUID, db: DbSession, settings: SettingsDep, tts: TTSDep) -> list[MediaAsset]:
    """Voice-over per scene with the free local Piper TTS."""
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


@router.get("/assets", response_model=list[AssetRead])
def list_assets(project_id: uuid.UUID, db: DbSession) -> list[MediaAsset]:
    return get_project_or_404(db, project_id).assets


def _scene_media(project, script) -> tuple[list[SceneMedia], list[int]]:
    latest: dict[tuple[AssetKind, int], MediaAsset] = {}
    for asset in project.assets:
        if asset.script_id == script.id and asset.scene_index is not None:
            latest[(asset.kind, asset.scene_index)] = asset
    scenes, missing = [], []
    for index, scene in enumerate(script.scenes):
        clip = latest.get((AssetKind.VIDEO_CLIP, index))
        visual = clip or latest.get((AssetKind.IMAGE, index))
        voice = latest.get((AssetKind.VOICEOVER, index))
        if visual is None or voice is None:
            missing.append(index)
            continue
        scenes.append(SceneMedia(Path(visual.uri), Path(voice.uri), scene["narration"], is_video=clip is not None))
    return scenes, missing


@router.post("/assemble", response_model=RenderJobRead, status_code=status.HTTP_201_CREATED)
def assemble(
    project_id: uuid.UUID, payload: AssembleRequest, db: DbSession, settings: SettingsDep, ffmpeg: FFmpegDep
) -> RenderJob:
    """Edit the final MP4 from the scene visuals and voice-over (FFmpeg)."""
    project = get_project_or_404(db, project_id)
    script = _latest_script(project)
    scenes, missing = _scene_media(project, script)
    if missing:
        raise HTTPException(status_code=409, detail=f"Missing visuals or voice for scenes {missing}.")
    music = Path(payload.music_path) if payload.music_path else None
    if music is not None and not music.is_file():
        raise HTTPException(status_code=422, detail="music_path does not exist.")

    spec = scaled(get_format_spec(project.format, settings), settings.edit_resolution_scale)
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

    work = _project_dir(settings, project.id) / f"script_{script.version}" / f"edit_{job.id.hex[:8]}"
    output = work.parent / f"final_{job.id.hex[:8]}.mp4"
    try:
        assemble_video(
            scenes, output, spec=spec, ffmpeg=ffmpeg, work_dir=work, music_path=music, subtitles=payload.subtitles
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
