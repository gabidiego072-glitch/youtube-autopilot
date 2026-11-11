"""Autonomous production pipeline.

A PipelineRun goes through fixed steps; each step is idempotent and records its
outcome, so a run can be resumed exactly where it stopped (after a crash, a quota
limit, or a human approval).

    topic -> research -> script -> fact_check -> voice -> storyboard -> render
          -> qa -> metadata -> thumbnail -> approval -> publish

Publishing never happens without an explicit approval unless the run was created
with auto_publish=True *and* YOUTUBE_PUBLISHING_ENABLED is on.
"""

from __future__ import annotations

import hashlib
import json
import logging
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.profile import scale_problems
from app.core.config import Settings
from app.core.errors import AutopilotError, ProviderError
from app.db.base import utcnow
from app.models import (
    Channel,
    Idea,
    MediaAsset,
    PipelineRun,
    PublishJob,
    RenderJob,
    ResearchBrief,
    Script,
    VideoMetadata,
    VideoProject,
)
from app.models.enums import (
    AssetKind,
    ContentCategory,
    FactCheckStatus,
    IdeaStatus,
    JobStatus,
    PrivacyStatus,
    ProjectStatus,
    PublishStatus,
    RunStatus,
    VideoFormat,
)
from app.services.ai.base import AIProvider, GenerationResult
from app.services.experiments import HOOKS, MUSIC, VOICES, choose_for_channel
from app.services.factcheck.checker import fact_check
from app.services.ideas.generator import generate_ideas
from app.services.learning.feedback import category_weights, top_premises
from app.services.metadata.generator import generate_metadata
from app.services.production.formats import DEFAULT_TARGET_DURATION, get_format_spec
from app.services.production.short import produce_short
from app.services.qa.video import QAError, check_video
from app.services.reporting.builder import performances
from app.services.research.briefing import build_brief
from app.services.scenes.check import check_scenes
from app.services.scenes.planner import plan_scenes
from app.services.scenes.recipe_planner import plan_with_recipes, replan
from app.services.scripts.generator import generate_script
from app.services.styles import POV_STORYBOARD_NOTE, city_note, next_city, next_planned_topic, pov_script_note
from app.services.thumbnails.generator import best_moment, generate_thumbnails
from app.services.variety import RECENT, RecentVideos, pick_idea, recent_videos
from app.services.youtube.base import UploadRequest
from app.services.youtube.data_api import YouTubeDataAPIPublisher
from render_engines.core.catalog import ENVIRONMENT_SCALES

logger = logging.getLogger(__name__)

STEPS = (
    "topic",
    "research",
    "script",
    "fact_check",
    "voice",
    "storyboard",
    "render",
    "qa",
    "metadata",
    "thumbnail",
    "approval",
    "publish",
)
SCRIPT_ATTEMPTS = 3
MIN_FRESH_IDEAS = 3


class UsageTracker:
    """Wraps the AI provider to count tokens per step (real cost tracking)."""

    def __init__(self, provider: AIProvider):
        self._provider = provider
        self.name = provider.name
        self.model = provider.model
        self.step = "unknown"
        self.by_step: dict[str, dict[str, int]] = {}

    def generate_json(self, *, system: str, prompt: str, schema: dict, images=None) -> GenerationResult:
        if images:
            result = self._provider.generate_json(system=system, prompt=prompt, schema=schema, images=images)
        else:
            result = self._provider.generate_json(system=system, prompt=prompt, schema=schema)
        bucket = self.by_step.setdefault(self.step, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        bucket["calls"] += 1
        bucket["input_tokens"] += result.usage.get("input_tokens", 0)
        bucket["output_tokens"] += result.usage.get("output_tokens", 0)
        return result


@dataclass
class Services:
    ai: AIProvider
    wiki: Any
    tts: Any
    blender: Any
    ffmpeg: Any
    settings: Settings
    log: Any = field(default=logger.info)
    trends: Any = None  # callable returning TrendSignals (best effort), or None
    publisher: Any = None  # defaults to the real YouTubeDataAPIPublisher
    voices: Any = None  # callable(voice_id) -> TTS, or None when that voice is not installed
    reuse_existing: bool = False  # resume: keep renders on disk even if made by an older code version


class StepBlocked(AutopilotError):
    """The step cannot continue without a person (approval) or a missing integration."""


class TopicRejected(StepBlocked):
    """The topic could not be turned into a scientifically sound script: try the next idea."""


MAX_TOPIC_RESTARTS = 2
DEFAULT_VOICE = "davefx"
TOPIC_STEPS = ("topic", "research", "script", "fact_check")


def _restart_with_next_idea(db, run, reason: str) -> None:
    """Drop the rejected project and idea, and run the topic steps again with the next idea."""
    project = db.get(VideoProject, run.project_id) if run.project_id else None
    if project is not None:
        project.status = ProjectStatus.ARCHIVED
        project.notes = f"Rejected automatically: {reason}"[:2000]
        if project.idea_id:
            idea = db.get(Idea, project.idea_id)
            if idea is not None:
                idea.status = IdeaStatus.REJECTED
    run.project_id = None
    for name in TOPIC_STEPS:
        _save_step(db, run, name, status="pending", error=None, detail=None)
    db.commit()


def create_run(
    db: Session,
    channel: Channel,
    video_format: VideoFormat = VideoFormat.SHORT,
    render_mode: str = "draft",
    auto_publish: bool = False,
) -> PipelineRun:
    run = PipelineRun(
        channel_id=channel.id,
        format=video_format,
        render_mode=render_mode,
        auto_publish=auto_publish,
        steps=[{"name": s, "status": "pending", "attempts": 0} for s in STEPS],
        usage={},
    )
    db.add(run)
    db.commit()
    return run


def _step(run: PipelineRun, name: str) -> dict:
    return next(s for s in run.steps if s["name"] == name)


def _save_step(db: Session, run: PipelineRun, name: str, **changes) -> None:
    steps = [dict(s) for s in run.steps]
    for s in steps:
        if s["name"] == name:
            s.update(changes)
    run.steps = steps  # reassign so the JSON column is flagged dirty
    db.commit()


def _work_dir(services: Services, run: PipelineRun) -> Path:
    return Path(services.settings.media_root) / "autopilot" / str(run.id)


# --- steps ---------------------------------------------------------------------------
def step_topic(db, run, services, ai) -> dict:
    channel = db.get(Channel, run.channel_id)
    fresh = list(
        db.scalars(
            select(Idea).where(Idea.channel_id == channel.id, Idea.status == IdeaStatus.NEW).order_by(Idea.score.desc())
        )
    )
    generated = 0
    used = set(db.scalars(select(VideoProject.working_title).where(VideoProject.channel_id == channel.id)))
    planned = next_planned_topic(used, channel.language) if services.settings.planned_topics_enabled else None
    if planned:  # a topic chosen by hand goes first, once
        idea = Idea(
            channel_id=channel.id,
            premise=planned["premise"][:300],
            category=ContentCategory(planned.get("category", ContentCategory.SOCIETY_AND_TECHNOLOGY.value)),
            hook=planned.get("hook", planned["premise"]),
            angle=planned.get("angle", ""),
            science_basis=planned.get("science_basis", ""),
            scores={},
            score=100.0,
            provider="planned",
            model="planned",
        )
        db.add(idea)
        db.commit()
        fresh = [idea]
    elif len(fresh) < MIN_FRESH_IDEAS:
        existing = list(db.scalars(select(Idea.premise).where(Idea.channel_id == channel.id)))
        existing += list(db.scalars(select(VideoProject.working_title).where(VideoProject.channel_id == channel.id)))
        past = performances(db, channel.id)
        signals = services.trends() if services.trends else None
        drafts = generate_ideas(
            ai,
            count=10,
            language=channel.language,
            existing_premises=existing,
            category_weights=category_weights(past),
            top_premises=top_premises(past),
            focus=channel.niche,
            trends=signals.prompt_text() if signals else None,
        )
        db.add_all([Idea(channel_id=channel.id, **d.model_dump()) for d in drafts])
        db.commit()
        generated = len(drafts)
        fresh = list(
            db.scalars(
                select(Idea)
                .where(Idea.channel_id == channel.id, Idea.status == IdeaStatus.NEW)
                .order_by(Idea.score.desc())
            )
        )
    if not fresh:
        raise ProviderError("No usable idea was generated.")
    idea = fresh[0] if planned else pick_idea(fresh, recent_videos(db, channel.id))
    project = VideoProject(
        channel_id=channel.id,
        working_title=idea.premise[:200],
        topic=f"{idea.premise}\nAngle: {idea.angle}\nScience: {idea.science_basis}\nHook idea: {idea.hook}",
        format=run.format,
        category=idea.category,
        idea_id=idea.id,
        target_duration_seconds=DEFAULT_TARGET_DURATION[run.format],
        language=channel.language,
    )
    db.add(project)
    db.flush()
    # Variants this video tries (voice, music, length, hook), chosen from past results.
    features = choose_for_channel(db, channel.id, seed=int(project.id.int % 100_000), language=channel.language)
    if run.format == VideoFormat.SHORT:
        project.target_duration_seconds = int(features["length"])
    else:
        features.pop("length")
    features["style"] = (planned or {}).get("style", services.settings.default_style)
    if planned and planned.get("city_style"):
        features["city_style"] = planned["city_style"]
    if planned and planned.get("notes"):
        project.notes = planned["notes"]
    if not features.get("city_style"):  # rotate through famous cities (New York, Paris, Tokyo, London)
        others = db.scalars(
            select(VideoProject.features)
            .where(VideoProject.channel_id == channel.id, VideoProject.id != project.id)
            .order_by(VideoProject.created_at.desc())
            .limit(8)
        )
        recent = [(f or {}).get("city_style", "") for f in others]
        features["city_style"] = next_city(recent)
        project.notes = "\n".join(n for n in (project.notes, city_note(features["city_style"])) if n)
    project.features = features
    idea.status, idea.project_id = IdeaStatus.USED, project.id
    run.project_id = project.id
    db.commit()
    return {
        "idea": idea.premise,
        "score": idea.score,
        "category": idea.category.value,
        "ideas_generated": generated,
        "variants": features,
    }


def _voice_tts(services, project):
    """The narrator chosen for this video (only used if a recording is missing), else the default."""
    voice = (project.features or {}).get("voice")
    return (services.voices(voice) if services.voices and voice else None) or services.tts


def _music_variant(project) -> int:
    """Progression from the experiment's music mood; key and tempo still vary with the seed."""
    seed = int(project.id.int % 100_000)
    mood = (project.features or {}).get("music")
    return (MUSIC.index(mood) if mood in MUSIC else seed % len(MUSIC)) + len(MUSIC) * (seed % 35)


def _style_note(project, pov_note: str) -> str | None:
    return pov_note if (project.features or {}).get("style") == "pov" else None


def _hook_note(project) -> str | None:
    hook = (project.features or {}).get("hook")
    return f"Hook style for this video: {HOOKS[hook]}" if hook in HOOKS else None


def _recent(db, project) -> RecentVideos:
    """Recent videos of the channel, excluding this one."""
    recent = recent_videos(db, project.channel_id, limit=RECENT + 1)
    own = (project.scripts[-1].title_question if project.scripts else None) or project.working_title
    if own in recent.titles:
        i = recent.titles.index(own)
        del recent.titles[i], recent.hooks[i]
    return recent


def _project(db, run) -> VideoProject:
    return db.get(VideoProject, run.project_id)


def _research(project) -> dict | None:
    if not project.research_briefs:
        return None
    brief = project.research_briefs[-1]
    return {"sources": brief.sources, "key_facts": brief.key_facts}


def step_research(db, run, services, ai) -> dict:
    project = _project(db, run)
    brief = build_brief(ai, services.wiki, premise=project.working_title, language=project.language)
    db.add(
        ResearchBrief(
            project_id=project.id,
            concepts=brief.concepts,
            sources=brief.sources,
            key_facts=brief.key_facts,
            status=brief.status,
            provider=brief.provider,
            model=brief.model,
        )
    )
    db.commit()
    return {
        "status": brief.status,
        "sources": len(brief.sources),
        "facts": len(brief.key_facts),
        "errors": brief.errors[:3],
    }


def _write_script(db, project, services, ai, notes: str | None = None) -> Script:
    last_error = None
    for _ in range(SCRIPT_ATTEMPTS):
        try:
            draft = generate_script(
                ai,
                spec=get_format_spec(project.format, services.settings),
                topic=project.topic,
                working_title=project.working_title,
                target_duration_seconds=project.target_duration_seconds,
                language=project.language,
                niche=project.channel.niche,
                style_guide=project.channel.style_guide,
                notes="\n".join(
                    n
                    for n in (
                        project.notes,
                        notes,
                        _style_note(project, pov_script_note(project.language)),
                        _hook_note(project),
                        _recent(db, project).script_note(),
                    )
                    if n
                )
                or None,
                research=_research(project),
            )
            break
        except ProviderError as exc:  # the rules rejected it: ask again
            last_error = exc
    else:
        raise last_error
    script = Script(
        project_id=project.id,
        version=len(project.scripts) + 1,
        title_question=draft.title_question,
        hook=draft.hook,
        scenes=[s.model_dump(mode="json") for s in draft.scenes],
        call_to_action=draft.call_to_action,
        ending_type=draft.ending_type,
        visual_bible=draft.visual_bible.model_dump(),
        full_text=draft.full_text,
        estimated_duration_seconds=draft.estimated_duration_seconds,
        provider=draft.provider,
        model=draft.model,
        prompt_version=draft.prompt_version,
    )
    db.add(script)
    if project.status == ProjectStatus.DRAFT:
        project.status = ProjectStatus.SCRIPT_READY
    db.commit()
    db.refresh(project)
    return script


def step_script(db, run, services, ai) -> dict:
    project = _project(db, run)
    script = _write_script(db, project, services, ai)
    return {
        "version": script.version,
        "title": script.title_question,
        "scenes": len(script.scenes),
        "estimated_seconds": script.estimated_duration_seconds,
    }


def step_fact_check(db, run, services, ai) -> dict:
    project = _project(db, run)
    for attempt in range(2):
        script = project.scripts[-1]
        result = fact_check(ai, premise=project.working_title, scenes=script.scenes, research=_research(project))
        script.fact_check_status, script.fact_check = result.status, result.as_record()
        db.commit()
        if result.status == FactCheckStatus.PASSED:
            return {"status": "passed", "script_version": script.version, "rewrites": attempt}
        if attempt == 0:  # one rewrite with the reviewer's corrections
            corrections = [
                f"- {v['claim']}: {v['note']} {v['correction']}".strip()
                for v in result.verdicts
                if v["verdict"] in ("incorrect", "mislabeled", "unverifiable")
            ]
            _write_script(db, project, services, ai, notes="Fix these fact-check findings:\n" + "\n".join(corrections))
    problems = [
        f"{v['claim']} ({v['verdict']})"
        for v in project.scripts[-1].fact_check.get("verdicts", [])
        if v.get("verdict") in ("incorrect", "mislabeled", "unverifiable")
    ][:3]
    raise TopicRejected("The script failed the fact-check twice: " + "; ".join(problems))


def step_voice(db, run, services, ai) -> dict:
    project = _project(db, run)
    script = project.scripts[-1]
    work = _work_dir(services, run)
    features = dict(project.features or {})
    tts = services.voices(features["voice"]) if services.voices and features.get("voice") else None
    if tts is None:  # voice not installed: use the default narrator and record it, so results stay honest
        tts = services.tts
        if features.get("voice"):
            features["voice"] = DEFAULT_VOICE
            project.features = features
    durations = []
    for i, scene in enumerate(script.scenes):
        wav = work / "voice" / f"scene_{i:02d}.wav"
        key = hashlib.sha256(f"{features.get('voice', '')}|{scene['narration']}".encode()).hexdigest()
        stamp = wav.with_suffix(".wav.key")
        if not (wav.is_file() and stamp.is_file() and stamp.read_text() == key):
            tts.synthesize(scene["narration"], wav)
            stamp.write_text(key)
            db.add(
                MediaAsset(
                    project_id=project.id,
                    script_id=script.id,
                    kind=AssetKind.VOICEOVER,
                    uri=str(wav),
                    mime_type="audio/wav",
                    size_bytes=wav.stat().st_size,
                    scene_index=i,
                    provider=f"{getattr(tts, 'name', 'tts')}:{features.get('voice', 'default')}",
                )
            )
        durations.append(services.ffmpeg.probe(wav).duration_seconds)
    db.commit()
    return {"scenes": len(durations), "voice_seconds": round(sum(durations), 2)}


def step_storyboard(db, run, services, ai) -> dict:
    project = _project(db, run)
    script = project.scripts[-1]
    work = _work_dir(services, run)
    durations = [
        max(1.0, services.ffmpeg.probe(work / "voice" / f"scene_{i:02d}.wav").duration_seconds + 0.3)
        for i in range(len(script.scenes))
    ]
    features = project.features or {}
    specs = None
    recipe_notes = "\n\n".join(n for n in (project.notes, _recent(db, project).recipe_note()) if n) or None
    if services.settings.recipes_enabled and features.get("style") == "pov":
        try:  # hand-made scene recipes: the AI only picks one per line
            specs = plan_with_recipes(
                ai,
                scenes=script.scenes,
                durations=durations,
                seed=int(project.id.int % 100_000),
                city=features.get("city_style") or "new_york",
                notes=recipe_notes,
            )
        except Exception as exc:  # noqa: BLE001 - never lose the day's video: fall back to the old storyboard
            services.log(f"recipe storyboard failed ({exc}); using the free-form storyboard")
    if specs and services.settings.scene_check_enabled and _can_render(services):
        specs, durations = _show_what_is_said(db, run, services, ai, specs, durations, recipe_notes)
    script.scene_specs = specs or plan_scenes(
        ai,
        scenes=script.scenes,
        durations=durations,
        visual_bible=script.visual_bible,
        seed=int(project.id.int % 100_000),
        variety_note="\n\n".join(
            n
            for n in (
                project.notes,
                _recent(db, project).storyboard_note(),
                _style_note(project, POV_STORYBOARD_NOTE),
            )
            if n
        )
        or None,
    )
    for spec in script.scene_specs:  # planned choices hold in every scene, whatever the AI wrote
        if features.get("style") == "pov" and spec["environment"].get("type") != "space":
            spec["camera"]["pov"] = True
        if features.get("city_style") and spec["environment"].get("type") in ("city", "coast"):
            spec["environment"]["style"] = features["city_style"]
    if specs:  # recipes choose the place: the script's scene scale follows it (a calm room may become the street)
        scenes = [dict(scene) for scene in script.scenes]
        for scene, spec in zip(scenes, script.scene_specs, strict=True):
            allowed = ENVIRONMENT_SCALES.get(spec["environment"].get("type"), ())
            if allowed and scene.get("scale") not in allowed:
                scene["scale"] = allowed[0]
        script.scenes = scenes
    db.commit()
    production = {
        "id": f"run_{run.id.hex[:8]}",
        "title_question": script.title_question,
        "format": project.format.value,
        "language": project.language,
        "seed": int(project.id.int % 100_000),
        "music_variant": _music_variant(project),
        "voice": (project.features or {}).get("voice", ""),
        "script": {
            "title_question": script.title_question,
            "hook": script.hook,
            "ending_type": script.ending_type,
            "ending_line": script.call_to_action,
            "visual_bible": script.visual_bible or {},
            "scenes": script.scenes,
        },
        "scenes": [
            {**spec, "duration_seconds": durations[i], "language": project.language}  # on-screen texts
            for i, spec in enumerate(script.scene_specs)
        ],
    }
    (work / "production.json").write_text(json.dumps(production, ensure_ascii=False, indent=2), encoding="utf-8")
    envs = sorted({s["environment"]["type"] for s in script.scene_specs})
    return {"scenes": len(script.scene_specs), "environments": envs}


def _can_render(services) -> bool:
    try:
        return bool(services.blender and services.blender.is_available())
    except Exception:  # noqa: BLE001
        return False


def _show_what_is_said(db, run, services, ai, specs, durations, notes):
    """Look at every scene before the long render: one that does not show its line is planned again."""
    project = _project(db, run)
    script = project.scripts[-1]
    work = _work_dir(services, run) / "check"
    seed = int(project.id.int % 100_000)
    city = (project.features or {}).get("city_style") or "new_york"
    scenes = [dict(s) for s in script.scenes]
    lines = [s["narration"] for s in scenes]
    first = check_scenes(ai, services.blender, specs, lines, work, seed)
    bad = {
        i: f'the line says "{lines[i]}"; the scene shows: {v["seen"]}; it needs: {v["missing"]}'
        for i, v in first.items()
        if not v["shows_it"]
    }
    services.log(f"scene check: {len(first) - len(bad)}/{len(first)} scenes show what their line says")
    report = {"first": {str(k): v for k, v in first.items()}, "replanned": sorted(bad)}
    if bad:
        try:
            specs = replan(
                ai, specs=specs, scenes=scenes, durations=durations, feedback=bad, seed=seed, city=city, notes=notes
            )
        except Exception as exc:  # noqa: BLE001 - keep the first storyboard rather than lose the video
            services.log(f"replanning failed ({exc}); keeping the first storyboard")
        again = check_scenes(ai, services.blender, specs, lines, work, seed, only=sorted(bad))
        report["second"] = {str(k): v for k, v in again.items()}
        still = sorted(i for i, v in again.items() if not v["shows_it"])
        report["still_failing"] = still
        services.log(f"scene check after replanning: {len(again) - len(still)}/{len(again)} fixed")
        # The lines are never rewritten to describe the picture: on Nov 11 that turned the story into
        # "you see a room with a blue sofa". A scene that still fails keeps its line; the script prompt is
        # what keeps lines filmable.
    work.mkdir(parents=True, exist_ok=True)
    (work / "scene_check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return specs, durations


def step_render(db, run, services, ai) -> dict:
    project = _project(db, run)
    script = project.scripts[-1]
    work = _work_dir(services, run)
    report = produce_short(
        work / "production.json",
        run.render_mode,
        work,
        blender=services.blender,
        ffmpeg=services.ffmpeg,
        tts=_voice_tts(services, project),
        log=services.log,
        reuse_existing=services.reuse_existing,
    )
    output = Path(report["output"])
    job = RenderJob(
        project_id=project.id,
        script_id=script.id,
        status=JobStatus.SUCCEEDED,
        width=int(report["resolution"].split("x")[0]),
        height=int(report["resolution"].split("x")[1]),
        fps=report["fps"],
        output_path=str(output),
        started_at=utcnow(),
        finished_at=utcnow(),
    )
    db.add(job)
    db.add(
        MediaAsset(
            project_id=project.id,
            script_id=script.id,
            kind=AssetKind.RENDER_OUTPUT,
            uri=str(output),
            mime_type="video/mp4",
            size_bytes=output.stat().st_size,
            provider="blender+ffmpeg",
        )
    )
    project.status = ProjectStatus.RENDERED
    db.commit()
    return {
        "output": str(output),
        "duration_seconds": report["duration_seconds"],
        "resolution": report["resolution"],
        "render_seconds": report["total_seconds"],
    }


def _render_output(run_detail: dict) -> Path:
    return Path(run_detail["output"])


def step_qa(db, run, services, ai) -> dict:
    project = _project(db, run)
    script = project.scripts[-1]
    output = _render_output(_step(run, "render")["detail"])
    work = _work_dir(services, run)
    try:
        result = check_video(
            output,
            frames=8,
            report_path=output.with_suffix(".report.json"),
            srt=work / run.render_mode / "edit" / "subtitles.srt",
            ffmpeg=services.ffmpeg.ffmpeg_binary,  # the same executables the render used
            ffprobe=services.ffmpeg.ffprobe_binary,
        )
    except QAError as exc:
        raise StepBlocked(f"Video QA could not analyse the video: {exc}") from exc
    scales = scale_problems([(s.get("scale", "street"), s["duration_seconds"]) for s in script.scenes])
    problems = result["problems"] + scales
    if problems:
        raise StepBlocked("Video QA failed: " + "; ".join(problems))
    return {
        "passed": True,
        "loudness_lufs": result["loudness_lufs"],
        "duration_seconds": result["duration_seconds"],
        "contact_sheet": result["contact_sheet"],
    }


def step_metadata(db, run, services, ai) -> dict:
    project = _project(db, run)
    script = project.scripts[-1]
    draft = generate_metadata(
        ai,
        video_format=project.format,
        working_title=script.title_question or project.working_title,
        script_text=script.full_text,
        language=project.language,
        ending_line=script.call_to_action,
        sources=project.research_briefs[-1].sources if project.research_briefs else None,
    )
    voice = VOICES.get((project.features or {}).get("voice", ""))
    if voice and voice.credit and voice.credit not in draft.description:
        draft.description = f"{draft.description}\n\n{voice.credit}"  # the voice's licence asks for it
    db.add(VideoMetadata(project_id=project.id, version=len(project.metadata_versions) + 1, **draft.model_dump()))
    project.status = ProjectStatus.METADATA_READY
    db.commit()
    return {"title": draft.title, "tags": len(draft.tags)}


def step_thumbnail(db, run, services, ai) -> dict:
    project = _project(db, run)
    script = project.scripts[-1]
    output = _render_output(_step(run, "render")["detail"])
    report = json.loads(output.with_suffix(".report.json").read_text())
    index, at = best_moment(report)
    clip = _work_dir(services, run) / run.render_mode / "clips" / f"scene_{index:02d}.mp4"
    metadata = db.scalar(
        select(VideoMetadata)
        .where(VideoMetadata.project_id == project.id)
        .order_by(VideoMetadata.version.desc())
        .limit(1)
    )
    text = (metadata.thumbnail_text if metadata else None) or script.hook
    paths = generate_thumbnails(
        services.ffmpeg, clip if clip.is_file() else output, at, text, _work_dir(services, run) / "thumbnails"
    )
    for path in paths.values():
        db.add(
            MediaAsset(
                project_id=project.id,
                script_id=script.id,
                kind=AssetKind.THUMBNAIL,
                uri=str(path),
                mime_type="image/jpeg",
                size_bytes=path.stat().st_size,
                provider="ffmpeg",
            )
        )
    db.commit()
    return {k: str(v) for k, v in paths.items()} | {"scene": index}


def step_approval(db, run, services, ai) -> dict:
    project = _project(db, run)
    if project.status == ProjectStatus.READY_TO_PUBLISH:
        return {"approved": True}
    if run.auto_publish and services.settings.youtube_publishing_enabled:
        project.status = ProjectStatus.READY_TO_PUBLISH  # the run itself was authorised to publish
        db.commit()
        return {"approved": True, "by": "auto_publish"}
    raise StepBlocked("Waiting for approval: review the video, then POST /projects/{id}/approve and resume the run.")


def step_publish(db, run, services, ai) -> dict:
    project = _project(db, run)
    metadata = project.metadata_versions[-1]
    output = _render_output(_step(run, "render")["detail"])
    publisher = services.publisher or YouTubeDataAPIPublisher(services.settings)
    publisher.check_ready()
    thumb = next(
        (Path(a.uri) for a in reversed(project.assets) if a.kind == AssetKind.THUMBNAIL and "1280x720" in a.uri), None
    )
    request = UploadRequest(
        video_path=output,
        title=metadata.title,
        description=metadata.description,
        tags=metadata.tags,
        category_id=metadata.category_id,
        privacy=PrivacyStatus(services.settings.youtube_default_privacy),
        thumbnail_path=thumb,
        comment=metadata.pinned_comment,
        language=project.language,
    )
    publisher.check_privacy(request)  # public needs YOUTUBE_ALLOW_PUBLIC=true, checked before uploading
    job = PublishJob(project_id=project.id, metadata_id=metadata.id, privacy=request.privacy)
    job.status = PublishStatus.UPLOADING
    db.add(job)
    db.commit()
    try:
        result = publisher.upload(request)
    except Exception as exc:
        job.status, job.error = PublishStatus.FAILED, getattr(exc, "message", str(exc))
        db.commit()
        raise
    job.status, job.youtube_video_id = PublishStatus.PUBLISHED, result.youtube_video_id
    job.error = "; ".join(result.warnings) or None
    project.youtube_video_id, project.status, project.published_at = (
        result.youtube_video_id,
        ProjectStatus.PUBLISHED,
        utcnow(),
    )
    db.commit()
    return {
        "youtube_video_id": result.youtube_video_id,
        "privacy": result.privacy,
        "thumbnail_set": result.thumbnail_set,
        "warnings": result.warnings,
    }


STEP_FUNCTIONS = {
    "topic": step_topic,
    "research": step_research,
    "script": step_script,
    "fact_check": step_fact_check,
    "voice": step_voice,
    "storyboard": step_storyboard,
    "render": step_render,
    "qa": step_qa,
    "metadata": step_metadata,
    "thumbnail": step_thumbnail,
    "approval": step_approval,
    "publish": step_publish,
}


def approve_run(db: Session, run: PipelineRun) -> VideoProject:
    """Human approval (same rules as POST /projects/{id}/approve): fact-checked script, metadata, finished render."""
    project = _project(db, run) if run.project_id else None
    if project is None:
        raise StepBlocked("This run has no project yet.")
    if not project.scripts or project.scripts[-1].fact_check_status != FactCheckStatus.PASSED:
        raise StepBlocked("The latest script has not passed the fact-check.")
    if not project.metadata_versions:
        raise StepBlocked("Metadata has not been generated yet.")
    if not any(job.status == JobStatus.SUCCEEDED for job in project.render_jobs):
        raise StepBlocked("There is no finished render to approve.")
    project.status = ProjectStatus.READY_TO_PUBLISH
    db.commit()
    return project


def run_pipeline(db: Session, run: PipelineRun, services: Services, until: str | None = None) -> PipelineRun:
    """Execute pending steps in order. Stops at the first failure or block; resumable."""
    tracker = UsageTracker(services.ai)
    run.status, run.error = RunStatus.RUNNING, None
    db.commit()
    restarts = 0
    pending = list(STEPS)
    while pending:
        name = pending.pop(0)
        step = _step(run, name)
        if step["status"] == "succeeded":
            continue
        run.current_step = name
        tracker.step = name
        _save_step(
            db,
            run,
            name,
            status="running",
            attempts=step.get("attempts", 0) + 1,
            started_at=utcnow().isoformat(),
            error=None,
        )
        services.log(f"[autopilot] {run.id} step {name}")
        try:
            detail = STEP_FUNCTIONS[name](db, run, services, tracker)
        except TopicRejected as exc:
            db.rollback()
            if restarts < MAX_TOPIC_RESTARTS:  # autonomous: drop this topic and try the next idea
                restarts += 1
                services.log(f"[autopilot] {run.id} topic rejected ({exc.message}); trying the next idea")
                _restart_with_next_idea(db, run, exc.message)
                pending = list(STEPS)
                continue
            _save_step(db, run, name, status="blocked", error=exc.message, finished_at=utcnow().isoformat())
            run.status, run.error = RunStatus.FAILED, f"{exc.message} (after trying {restarts + 1} topics)"
            break
        except StepBlocked as exc:
            db.rollback()
            _save_step(db, run, name, status="blocked", error=exc.message, finished_at=utcnow().isoformat())
            run.status = RunStatus.WAITING_APPROVAL if name == "approval" else RunStatus.FAILED
            run.error = exc.message
            break
        except AutopilotError as exc:
            db.rollback()
            _save_step(db, run, name, status="failed", error=exc.message, finished_at=utcnow().isoformat())
            run.status, run.error = RunStatus.FAILED, f"{name}: {exc.message}"
            break
        except Exception as exc:  # noqa: BLE001 - record any crash so the run can be inspected and resumed
            db.rollback()
            logger.exception("autopilot step %s crashed", name)
            _save_step(
                db,
                run,
                name,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                detail={"traceback": traceback.format_exc()[-2000:]},
                finished_at=utcnow().isoformat(),
            )
            run.status, run.error = RunStatus.FAILED, f"{name}: {type(exc).__name__}: {exc}"
            break
        _save_step(db, run, name, status="succeeded", detail=detail, finished_at=utcnow().isoformat())
        if until and name == until:
            break
    else:
        run.status = RunStatus.PUBLISHED
    totals = {"input_tokens": 0, "output_tokens": 0}
    merged = dict((run.usage or {}).get("by_step", {}))
    for step_name, bucket in tracker.by_step.items():
        previous = merged.get(step_name, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        merged[step_name] = {k: previous.get(k, 0) + bucket[k] for k in bucket}
    for bucket in merged.values():
        totals["input_tokens"] += bucket["input_tokens"]
        totals["output_tokens"] += bucket["output_tokens"]
    run.usage = {**totals, "by_step": merged}
    if run.status in (RunStatus.PUBLISHED, RunStatus.FAILED):
        run.finished_at = utcnow()
    db.commit()
    return run
