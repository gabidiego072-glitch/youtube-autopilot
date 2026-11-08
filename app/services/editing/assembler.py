"""Final edit with FFmpeg only (free).

Timeline: each scene lasts as long as its voice-over plus a short pause. Scenes are
joined with a cross-dissolve ('fade') or a hard cut; to keep the voice in sync, a
scene's clip is rendered longer by the length of the following transition, so the
dissolve eats that tail instead of shifting the timeline.

Audio: voices placed at their exact times, sound effects on cue, a music bed that
ducks under the narration, loudness normalised to YouTube's -14 LUFS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.services.production.formats import FormatSpec
from app.services.rendering.ffmpeg import FFmpeg, ProbeResult, escape_filter_value, write_srt

SCENE_PAUSE = 0.3  # breathing room after each line
VOICE_LEAD = 0.06  # voice starts just after the cut
MIN_SCENE = 1.5
TRANSITIONS = {"cut": 0.0, "fade": 0.35}
SFX_GAIN = {"whoosh": 0.9, "impact": 1.0, "rumble": 0.8, "wind": 0.7, "chime": 0.6}


@dataclass(frozen=True)
class SceneSlot:
    start: float  # position of the scene in the final video (s)
    duration: float  # time the scene owns before the next one starts (s)
    clip_length: float  # rendered clip length = duration + next transition
    transition_in: str
    transition_seconds: float


def plan_timeline(speech: list[float], transitions: list[str], fps: int, pause: float = SCENE_PAUSE) -> list[SceneSlot]:
    """Scene slots from voice durations. transitions[i] is the transition INTO scene i."""
    if len(speech) != len(transitions):
        raise ValueError("One transition per scene is required.")
    frame = 1 / fps
    # A hard cut is a one-frame dissolve, so the same filter graph handles both.
    lengths = [max(TRANSITIONS.get(t, TRANSITIONS["fade"]), frame) for t in transitions]
    slots, start = [], 0.0
    for i, voice in enumerate(speech):
        duration = round(max(MIN_SCENE, VOICE_LEAD + voice + pause) / frame) * frame
        tail = lengths[i + 1] if i + 1 < len(speech) else 0.0
        slots.append(
            SceneSlot(
                round(start, 4),
                round(duration, 4),
                round(duration + tail, 4),
                transitions[i] if i else "cut",
                lengths[i] if i else 0.0,
            )
        )
        start += duration
    return slots


@dataclass(frozen=True)
class EditScene:
    clip: Path
    voice: Path
    subtitle: str
    speech: float
    slot: SceneSlot
    sfx: list = field(default_factory=list)  # [(path, kind, at_seconds_in_scene)]
    hud: str = ""  # counter shown at the top for the whole scene (POV videos)


def subtitle_cues(scenes: list[EditScene], words_per_cue: int) -> list[dict]:
    """Short cues timed across each voice line, proportional to their length in characters."""
    cues = []
    for scene in scenes:
        words = scene.subtitle.split()
        if not words:
            continue
        chunks = [" ".join(words[i : i + words_per_cue]) for i in range(0, len(words), words_per_cue)]
        total = sum(len(c) + 1 for c in chunks)
        t = scene.slot.start + VOICE_LEAD
        for chunk in chunks:
            length = scene.speech * (len(chunk) + 1) / total
            cues.append({"start": round(t, 3), "end": round(t + length, 3), "text": chunk})
            t += length
    return cues


def subtitle_style(portrait: bool) -> str:
    size, margin = (15, 78) if portrait else (16, 22)
    return (
        f"FontName=Inter,FontSize={size},Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,"
        f"BackColour=&H64000000,BorderStyle=1,Outline=2.2,Shadow=1.2,Alignment=2,MarginV={margin},"
        f"MarginL=26,MarginR=26"
    )


def hud_style(portrait: bool) -> str:
    size, margin = (13, 40) if portrait else (13, 16)
    return (
        f"FontName=Inter,FontSize={size},Bold=1,PrimaryColour=&H0040D8FF,OutlineColour=&H00101010,"
        f"BorderStyle=1,Outline=1.6,Shadow=0.8,Alignment=6,MarginV={margin},Spacing=1.2"
    )


def assemble_video(
    scenes: list[EditScene],
    output_path: Path,
    *,
    spec: FormatSpec,
    ffmpeg: FFmpeg,
    work_dir: Path,
    music_path: Path | None = None,
    subtitles: bool = True,
    crf: int = 18,
    preset: str = "medium",
) -> ProbeResult:
    if not scenes:
        raise ValueError("Nothing to assemble.")
    work_dir.mkdir(parents=True, exist_ok=True)
    w, h, fps = spec.width, spec.height, spec.fps
    total = scenes[-1].slot.start + scenes[-1].slot.duration
    args = [ffmpeg.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error"]
    graph = []

    # --- video: normalise every clip, then chain the transitions ----------
    for i, scene in enumerate(scenes):
        args += ["-i", str(scene.clip)]
        graph.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1,"
            f"format=yuv420p,tpad=stop_mode=clone:stop_duration=2,trim=duration={scene.slot.clip_length:.4f},"
            f"setpts=PTS-STARTPTS[c{i}]"
        )
    current = "c0"
    for i, scene in enumerate(scenes[1:], start=1):
        graph.append(
            f"[{current}][c{i}]xfade=transition=fade:duration={scene.slot.transition_seconds:.4f}:"
            f"offset={scene.slot.start:.4f}[x{i}]"
        )
        current = f"x{i}"
    hud_cues = [
        {"start": round(s.slot.start, 3), "end": round(s.slot.start + s.slot.duration, 3), "text": s.hud.strip()}
        for s in scenes
        if s.hud.strip()
    ]
    if hud_cues:  # e.g. "DÍA 2 · 21:10", top of the frame, above everything
        hud = write_srt(hud_cues, work_dir / "hud.srt")
        graph.append(
            f"[{current}]subtitles=filename={escape_filter_value(str(hud))}:force_style='{hud_style(h > w)}'[hud]"
        )
        current = "hud"
    if subtitles:
        cues = subtitle_cues(scenes, 4 if h > w else 8)
        srt = write_srt(cues, work_dir / "subtitles.srt")
        graph.append(
            f"[{current}]subtitles=filename={escape_filter_value(str(srt))}:force_style='{subtitle_style(h > w)}'[vout]"
        )
    else:
        graph.append(f"[{current}]null[vout]")

    # --- audio: voices on their exact times, effects on cue, ducked music --
    index = len(scenes)
    voice_labels, sfx_labels = [], []
    for i, scene in enumerate(scenes):
        args += ["-i", str(scene.voice)]
        delay = round((scene.slot.start + VOICE_LEAD) * 1000)
        graph.append(f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={delay}:all=1[vo{i}]")
        voice_labels.append(f"[vo{i}]")
        index += 1
    for i, scene in enumerate(scenes):
        for j, (path, kind, at) in enumerate(scene.sfx):
            args += ["-i", str(path)]
            delay = round(max(0.0, scene.slot.start + at) * 1000)
            gain = SFX_GAIN.get(kind, 0.8)
            graph.append(
                f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,volume={gain},"
                f"adelay={delay}:all=1[fx{i}_{j}]"
            )
            sfx_labels.append(f"[fx{i}_{j}]")
            index += 1
    graph.append(
        f"{''.join(voice_labels)}amix=inputs={len(voice_labels)}:normalize=0:duration=longest,volume=1.6[speech]"
    )
    graph.append("[speech]asplit=2[speech_out][speech_key]")
    mix_inputs = ["[speech_out]"]
    if music_path is not None:
        args += ["-i", str(music_path)]
        graph.append(f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,volume=1.0[music]")
        graph.append("[music][speech_key]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=450[ducked]")
        mix_inputs.append("[ducked]")
        index += 1
    else:
        graph.append("[speech_key]anullsink")
    if sfx_labels:
        graph.append(f"{''.join(sfx_labels)}amix=inputs={len(sfx_labels)}:normalize=0:duration=longest[fxbus]")
        mix_inputs.append("[fxbus]")
    graph.append(
        f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:normalize=0:duration=longest,"
        f"atrim=duration={total:.4f},loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    script = work_dir / "filter_graph.txt"
    script.write_text(";\n".join(graph), encoding="utf-8")
    ffmpeg.run(
        [
            *args,
            "-filter_complex_script",
            str(script),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-t",
            f"{total:.4f}",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return ffmpeg.probe(output_path)
