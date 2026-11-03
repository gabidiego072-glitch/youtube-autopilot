"""Produce a complete Short from a production file (script + one 3D scene spec per scene).

    voice (Piper) -> timeline from the real voice lengths -> Blender renders every scene
    (retimed to its slot) -> sound effects + music -> FFmpeg edit -> report

The production file is exactly what the API stores for a project (script + storyboard),
so the same code produces any script, by hand or from the automatic pipeline.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from app.models.enums import VideoFormat
from app.services.audio.synth import SFX, generate_music, generate_sfx
from app.services.editing.assembler import EditScene, assemble_video, plan_timeline
from app.services.production.formats import FormatSpec
from app.services.production.modes import RenderMode, get_mode
from app.services.rendering.blender import Blender
from app.services.rendering.ffmpeg import FFmpeg
from app.services.rendering.scene3d import render_scene_video
from app.services.scripts.generator import ScriptDraft, structure_problems
from render_engines.core.retime import retime
from render_engines.core.spec import SpecError, build_context, validate_spec

__all__ = ["load_production", "produce_short", "scene_effects", "output_format", "timed_spec"]


class ProductionError(ValueError):
    pass


def load_production(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    script, specs = data.get("script", {}), data.get("scenes", [])
    if len(specs) != len(script.get("scenes", [])):
        raise ProductionError("The production needs one 3D scene per script scene.")
    draft = ScriptDraft(**script, provider="production", model="file")
    problems = structure_problems(draft, VideoFormat(data.get("format", "short")))
    if problems:
        raise ProductionError("Script rejected: " + " ".join(problems))
    for i, spec in enumerate(specs):
        try:
            validate_spec({"engine": "cinematic", "fps": 24, "seed": data.get("seed", 0), **spec})
        except SpecError as exc:
            raise ProductionError(f"Scene {i}: {exc}") from exc
        for effect in spec.get("sfx", []):
            if effect.get("type") not in SFX:
                raise ProductionError(f"Scene {i}: unknown sound effect '{effect.get('type')}'.")
    return data


def _cached(path: Path, key: str) -> bool:
    stamp = path.with_suffix(path.suffix + ".key")
    return path.is_file() and stamp.is_file() and stamp.read_text() == key


def _stamp(path: Path, key: str) -> None:
    path.with_suffix(path.suffix + ".key").write_text(key)


def scene_effects(ffmpeg: FFmpeg, spec: dict, slot, cache_dir: Path) -> list:
    """Sound effects of a scene, generated once, with their cue time scaled to the slot."""
    effects = []
    for effect in spec.get("sfx", []):
        path = cache_dir / f"{effect['type']}.wav"
        if not path.is_file():
            generate_sfx(ffmpeg, effect["type"], path)
        planned = float(spec.get("duration_seconds") or slot.duration)
        effects.append((path, effect["type"], effect.get("at", 0.0) * slot.duration / planned))
    return effects


def output_format(video_format: str, quality: str) -> FormatSpec:
    aspect = "9:16" if video_format == "short" else "16:9"
    ctx = build_context({"engine": "cinematic", "duration_seconds": 1, "fps": 24}, aspect, quality)
    return FormatSpec(VideoFormat(video_format), ctx.width, ctx.height, 24, 1, None, "", "")


def _timed_spec(spec: dict, slot, seed: int, mode: RenderMode) -> dict:
    """Engine spec for one scene: actions retimed to the voice slot, plus the transition tail."""
    full = {"engine": "cinematic", "fps": 24, "seed": seed, "motion_blur": False, **spec}
    timed = retime(full, slot.duration)
    timed["duration_seconds"] = round(slot.clip_length, 4)
    timed["motion_blur"] = bool(spec.get("motion_blur", False) and mode.motion_blur)
    return timed


def produce_short(
    production_path: Path,
    mode_name: str,
    out_dir: Path,
    *,
    blender: Blender,
    ffmpeg: FFmpeg,
    tts,
    scenes: list[int] | None = None,
    threads: int = 0,
    log=print,
) -> dict:
    started = time.monotonic()
    production = load_production(production_path)
    mode: RenderMode = get_mode("preview" if mode_name == "plan" else mode_name)
    script, specs = production["script"], production["scenes"]
    seed = production.get("seed", 0)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Voice (cached by text): its length sets the length of every scene.
    voices, speech = [], []
    for i, scene in enumerate(script["scenes"]):
        wav = out_dir / "voice" / f"scene_{i:02d}.wav"
        key = hashlib.sha256(scene["narration"].encode()).hexdigest()
        if not _cached(wav, key):
            tts.synthesize(scene["narration"], wav)
            _stamp(wav, key)
        voices.append(wav)
        speech.append(ffmpeg.probe(wav).duration_seconds)

    transitions = [spec.get("transition", "fade") for spec in specs]
    slots = plan_timeline(speech, transitions, fps=24)

    if mode_name == "plan":
        return {
            "timed_specs": [_timed_spec(specs[i], slots[i], seed, mode) for i in range(len(specs))],
            "timeline": [asdict(s) for s in slots],
            "speech": speech,
        }

    # 2. Which scenes: everything for draft/final; a 5-10 s fragment for preview.
    if mode.full_video:
        selected = list(range(len(specs)))
    else:
        selected = scenes or [0]
        if sum(slots[i].duration for i in selected) > mode.max_seconds:
            raise ProductionError(f"Preview fragments are limited to {mode.max_seconds:.0f} s; pick fewer scenes.")
    if scenes and mode.full_video and sorted(scenes) != selected:
        raise ProductionError("draft and final always render every scene.")

    # 3. Render each selected scene, retimed to its slot (+ the next transition's tail).
    clips, render_times = {}, {}
    for i in selected:
        slot = slots[i]
        timed = _timed_spec(specs[i], slot, seed, mode)
        spec_path = out_dir / mode.name / "specs" / f"scene_{i:02d}.json"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(json.dumps(timed, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"[produce] scene {i}: {slot.clip_length:.2f}s ({mode.name})")
        t0 = time.monotonic()
        result = render_scene_video(
            spec_path,
            out_dir / mode.name / "clips" / f"scene_{i:02d}.mp4",
            blender=blender,
            ffmpeg=ffmpeg,
            aspect="9:16" if production.get("format", "short") == "short" else "16:9",
            quality=mode.quality,
            subtitles=False,
            threads=threads,
            motion_blur=timed["motion_blur"],
            work_dir=out_dir / mode.name / "work" / f"scene_{i:02d}",
        )
        clips[i] = result.video_path
        render_times[i] = round(time.monotonic() - t0, 1)

    # 4. Sound effects and music (generated, cached).
    edit_scenes, offset = [], selected and slots[selected[0]].start
    for i in selected:
        effects = scene_effects(ffmpeg, specs[i], slots[i], out_dir / "sfx") if mode.sfx else []
        slot = slots[i]
        rebased = type(slot)(
            round(slot.start - offset, 4), slot.duration, slot.clip_length, slot.transition_in, slot.transition_seconds
        )
        edit_scenes.append(
            EditScene(
                clips[i],
                voices[i],
                script["scenes"][i].get("subtitle") or script["scenes"][i]["narration"],
                speech[i],
                rebased,
                effects,
            )
        )
    total = edit_scenes[-1].slot.start + edit_scenes[-1].slot.duration
    music = None
    if mode.music:
        music = out_dir / mode.name / "music.wav"
        generate_music(ffmpeg, total + 1.0, music)

    # 5. Edit.
    spec = output_format(production.get("format", "short"), mode.quality)
    output = out_dir / f"{production.get('id', 'short')}_{mode.name}.mp4"
    t0 = time.monotonic()
    probe = assemble_video(
        edit_scenes,
        output,
        spec=spec,
        ffmpeg=ffmpeg,
        work_dir=out_dir / mode.name / "edit",
        music_path=music,
        crf=mode.crf,
        preset=mode.preset,
    )
    report = {
        "output": str(output),
        "mode": mode.name,
        "resolution": f"{probe.width}x{probe.height}",
        "fps": 24,
        "duration_seconds": round(probe.duration_seconds, 3),
        "has_audio": probe.has_audio,
        "scenes": [
            {
                "index": i,
                "beat": script["scenes"][i]["beat"],
                "start": e.slot.start,
                "duration": e.slot.duration,
                "voice_seconds": round(speech[i], 3),
                "transition": e.slot.transition_in,
                "render_seconds": render_times[i],
                "sfx": [k for _, k, _ in e.sfx],
            }
            for i, e in zip(selected, edit_scenes, strict=True)
        ],
        "edit_seconds": round(time.monotonic() - t0, 1),
        "total_seconds": round(time.monotonic() - started, 1),
        "timeline": [asdict(slots[i]) for i in selected],
    }
    (out_dir / f"{production.get('id', 'short')}_{mode.name}.report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def timed_spec(spec: dict, slot, seed: int, mode_name: str) -> dict:
    return _timed_spec(spec, slot, seed, get_mode(mode_name))
