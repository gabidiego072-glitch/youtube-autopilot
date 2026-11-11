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
from app.services.editing.assembler import ColdOpen, EditScene, SceneSlot, assemble_video, plan_timeline
from app.services.production.formats import FormatSpec
from app.services.production.modes import RenderMode, get_mode
from app.services.rendering.blender import Blender
from app.services.rendering.ffmpeg import FFmpeg
from app.services.rendering.scene3d import render_scene_video
from app.services.scenes.planner import environment_scale_problem
from app.services.scripts.generator import ScriptDraft, structure_problems
from render_engines.core.retime import retime
from render_engines.core.spec import SpecError, build_context, engine_fingerprint, validate_spec

__all__ = [
    "load_production",
    "produce_short",
    "render_clip",
    "render_scene_shard",
    "scene_effects",
    "output_format",
    "shard_scenes",
    "timed_spec",
]


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
        mismatch = environment_scale_problem(spec, script["scenes"][i].get("scale", "street"))
        if mismatch:
            raise ProductionError(f"Scene {i}: {mismatch}")
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


COLD_OPEN_SECONDS = 1.6
_STRIKING = ("collapse", "fire", "flood", "surge", "fling", "inertia_shock", "shatter_windows", "fall")


def scene_hud(scenes: list[dict], i: int) -> str:
    """The counter of scene i; a word like 'LOOP' is not a counter: keep the previous one on screen."""
    hud = (scenes[i].get("hud") or "").strip()
    if any(w in hud.upper() for w in ("LOOP", "BUCLE")):
        return scene_hud(scenes, i - 1) if i > 0 else ""
    return hud


def cold_open_scene(specs: list[dict], selected: list[int]) -> int | None:
    """The most striking scene to open the video with (a chase, a collapse, a fire...), never the first."""

    def score(i: int) -> int:
        spec = specs[i]
        env = spec.get("environment", {})
        kinds = {a.get("type") for a in spec.get("actions", [])}
        points = 5 if spec.get("recipe") == "street_run" else 0
        points += 4 * bool(kinds & set(_STRIKING[:5])) + 2 * ("fall" in kinds)
        points += 3 * bool(env.get("chasers") or env.get("zombies")) + 2 * bool(env.get("panic"))
        points += 2 * bool(spec.get("look"))
        points += 4 * (spec.get("recipe") == "meet_person")  # the story's own moment (meeting someone)
        points += 3 * any(c.get("pose") == "sit" for c in spec.get("characters", []))
        points += 1 * any(p.get("id") == "stat" for p in spec.get("props", []))
        return points

    candidates = [i for i in selected[1:]]
    if not candidates:
        return None
    best = max(candidates, key=score)
    return best if score(best) > 0 else None


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
    if spec.get("parts"):  # one sub-scene per beat of the line, each retimed to its share of the voice
        shares = spec.get("shares") or [1 / len(spec["parts"])] * len(spec["parts"])
        total = sum(shares) or 1.0
        timed_parts = []
        for j, (part, share) in enumerate(zip(spec["parts"], shares, strict=True)):
            length = slot.duration * share / total
            part_full = {"engine": "cinematic", "fps": 24, "seed": seed, "motion_blur": False, **part}
            piece = retime(part_full, length)
            if j == len(shares) - 1:  # the last piece also covers the transition into the next line
                piece["duration_seconds"] = round(length + slot.clip_length - slot.duration, 4)
            piece["motion_blur"] = timed["motion_blur"]
            timed_parts.append(piece)
        timed["parts"] = timed_parts
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
    reuse_existing: bool = False,
) -> dict:
    """reuse_existing: keep any voice recording and rendered clip already on disk even if its cache key
    does not match (to finish a run whose renders were made by an older version of the code)."""
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
        # Same key as the autopilot's voice step: "<voice id>|<text>", so its recordings are reused as-is
        # (with the narrator chosen for this video) instead of being redone with the default voice.
        key = hashlib.sha256(f"{production.get('voice', '')}|{scene['narration']}".encode()).hexdigest()
        if not (_cached(wav, key) or (reuse_existing and wav.is_file())):
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
        clips[i], render_times[i] = render_clip(
            production,
            i,
            slots[i],
            mode,
            out_dir,
            blender=blender,
            ffmpeg=ffmpeg,
            threads=threads,
            log=log,
            reuse_existing=reuse_existing,
        )

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
                scene_hud(script["scenes"], i),
            )
        )
    total = edit_scenes[-1].slot.start + edit_scenes[-1].slot.duration
    music = None
    if mode.music:
        music = out_dir / mode.name / "music.wav"
        generate_music(
            ffmpeg,
            total + COLD_OPEN_SECONDS + 1.0,
            music,
            variant=production.get("music_variant", production.get("seed", 0)),
        )

    # 5. Edit, opening on the most striking moment with the title over it.
    opening = None
    if mode.full_video and production.get("cold_open", True) and len(selected) > 2:
        k = cold_open_scene(specs, selected)
        if k is not None and script.get("title_question"):
            fx_dir = out_dir / "sfx"
            hits = []
            for kind, at in (("impact", 0.0), ("rumble", 0.0), ("whoosh", COLD_OPEN_SECONDS - 0.35)):
                path = fx_dir / f"{kind}.wav"
                if not path.is_file():
                    generate_sfx(ffmpeg, kind, path)
                hits.append((path, kind, at))
            excerpt = max(0.0, min(slots[k].duration * 0.45, slots[k].clip_length - COLD_OPEN_SECONDS))
            opening = ColdOpen(clips[k], excerpt, COLD_OPEN_SECONDS, script.get("title_question", ""), hits)
    spec = output_format(production.get("format", "short"), mode.output_quality or mode.quality)
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
        cold_open=opening,
    )
    report = {
        "cold_open": {"clip": str(opening.clip), "start": opening.start} if opening else None,
        # The story starts after the opening: scene starts below are story times, add this for video times.
        "lead_seconds": opening.length if opening else 0.0,
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


def clip_path(out_dir: Path, mode_name: str, index: int) -> Path:
    return out_dir / mode_name / "clips" / f"scene_{index:02d}.mp4"


def render_clip(
    production: dict,
    index: int,
    slot,
    mode: RenderMode,
    out_dir: Path,
    *,
    blender,
    ffmpeg,
    threads=0,
    log=print,
    reuse_existing: bool = False,
) -> tuple[Path, float]:
    """Render one scene to a silent clip. A clip whose spec, quality and engine code are unchanged is
    reused, so scenes rendered on other machines (parallel cloud jobs) are picked up by the final edit."""
    timed = _timed_spec(production["scenes"][index], slot, production.get("seed", 0), mode)
    aspect = "9:16" if production.get("format", "short") == "short" else "16:9"
    spec_path = out_dir / mode.name / "specs" / f"scene_{index:02d}.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_json = json.dumps(timed, ensure_ascii=False, indent=2, sort_keys=True)
    spec_path.write_text(spec_json, encoding="utf-8")
    key = hashlib.sha256(f"{spec_json}|{mode.quality}|{aspect}|{engine_fingerprint()}".encode()).hexdigest()
    output = clip_path(out_dir, mode.name, index)
    if _cached(output, key) or (reuse_existing and output.is_file() and output.stat().st_size > 0):
        log(f"[produce] scene {index}: reusing rendered clip")
        return output, 0.0
    log(f"[produce] scene {index}: {slot.clip_length:.2f}s ({mode.name})")
    t0 = time.monotonic()
    if timed.get("parts"):
        _render_parts(timed, spec_path, output, aspect, mode, blender, ffmpeg, threads, out_dir, index)
        _stamp(output, key)
        return output, round(time.monotonic() - t0, 1)
    render_scene_video(
        spec_path,
        output,
        blender=blender,
        ffmpeg=ffmpeg,
        aspect=aspect,
        quality=mode.quality,
        subtitles=False,
        threads=threads,
        motion_blur=timed["motion_blur"],
        work_dir=out_dir / mode.name / "work" / f"scene_{index:02d}",
    )
    _stamp(output, key)
    return output, round(time.monotonic() - t0, 1)


def _render_parts(timed, spec_path, output, aspect, mode, blender, ffmpeg, threads, out_dir, index) -> None:
    """A line made of several beats: every sub-scene is rendered on its own, then they are cut together."""
    work = out_dir / mode.name / "work" / f"scene_{index:02d}"
    pieces = []
    for j, part in enumerate(timed["parts"]):
        part_spec = spec_path.with_name(f"scene_{index:02d}_part{j}.json")
        part_spec.write_text(json.dumps(part, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        piece = work / f"part_{j}.mp4"
        render_scene_video(
            part_spec,
            piece,
            blender=blender,
            ffmpeg=ffmpeg,
            aspect=aspect,
            quality=mode.quality,
            subtitles=False,
            threads=threads,
            motion_blur=part["motion_blur"],
            work_dir=work / f"part_{j}",
        )
        pieces.append(piece)
    ffmpeg.concat_clips(pieces, output)


def shard_scenes(count: int, shard: int, shards: int) -> list[int]:
    """Scenes for one of several parallel render jobs (round-robin keeps the shards balanced)."""
    if shards < 1 or not 0 <= shard < shards:
        raise ProductionError(f"Invalid shard {shard}/{shards}.")
    return list(range(shard, count, shards))


def render_scene_shard(
    production_path: Path,
    mode_name: str,
    out_dir: Path,
    *,
    blender,
    ffmpeg,
    tts,
    shard: int,
    shards: int,
    threads: int = 0,
    log=print,
) -> dict:
    """Render only this shard's scenes (clips only, no edit). Run the full production afterwards to edit."""
    plan = produce_short(production_path, "plan", out_dir, blender=blender, ffmpeg=ffmpeg, tts=tts, log=log)
    production = load_production(production_path)
    mode = get_mode(mode_name)
    if not mode.full_video:
        raise ProductionError("Parallel rendering is for draft/final/hd videos.")
    slots = [SceneSlot(**t) for t in plan["timeline"]]
    done = {}
    for i in shard_scenes(len(slots), shard, shards):
        path, seconds = render_clip(
            production, i, slots[i], mode, out_dir, blender=blender, ffmpeg=ffmpeg, threads=threads, log=log
        )
        done[i] = {"clip": str(path), "render_seconds": seconds}
    return {"shard": shard, "shards": shards, "mode": mode.name, "scenes": done}


def timed_spec(spec: dict, slot, seed: int, mode_name: str) -> dict:
    return _timed_spec(spec, slot, seed, get_mode(mode_name))
