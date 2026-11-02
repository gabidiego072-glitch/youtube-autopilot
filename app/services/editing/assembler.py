"""Final edit with FFmpeg only (free): one shot per scene, cut to the length of its
voice-over, with slow camera motion on stills ("Ken Burns") or the AI clip itself,
then subtitles timed to the narration and an optional music bed that ducks under
the voice."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.production.formats import FormatSpec
from app.services.rendering.ffmpeg import FFmpeg, ProbeResult, escape_filter_value, write_srt

SCENE_PAUSE = 0.25  # seconds of breathing room after each scene's narration
MIN_SCENE = 1.2


@dataclass(frozen=True)
class SceneMedia:
    visual: Path
    audio: Path
    narration: str
    is_video: bool = False


def subtitle_cues(narrations: list[str], speech: list[float], starts: list[float], words_per_cue: int) -> list[dict]:
    """Split each scene's narration into short cues, timed by word count within its speech."""
    cues = []
    for text, duration, start in zip(narrations, speech, starts, strict=True):
        words = text.split()
        if not words:
            continue
        per_word = duration / len(words)
        for i in range(0, len(words), words_per_cue):
            chunk = words[i : i + words_per_cue]
            cue_start = start + i * per_word
            cues.append(
                {
                    "start": round(cue_start, 3),
                    "end": round(cue_start + len(chunk) * per_word, 3),
                    "text": " ".join(chunk),
                }
            )
    return cues


def _shot_filter(spec: FormatSpec, frames: int, index: int) -> str:
    w, h, fps = spec.width, spec.height, spec.fps
    zoom = 0.10
    step = zoom / max(frames, 1)
    # Even scenes push in slowly, odd scenes pull out.
    z = f"min(1+{step:.6f}*on,{1 + zoom})" if index % 2 == 0 else f"max({1 + zoom}-{step:.6f}*on,1)"
    drift = f"+(on/{frames})*iw*0.02" if index % 3 == 1 else ""
    return (
        f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2){drift}':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={fps},"
        f"setsar=1,format=yuv420p"
    )


def _clip_filter(spec: FormatSpec, duration: float) -> str:
    w, h = spec.width, spec.height
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={spec.fps},"
        f"trim=duration={duration:.3f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p"
    )


def subtitle_style(portrait: bool) -> str:
    size, margin = (15, 75) if portrait else (16, 20)
    return (
        f"FontName=Inter,FontSize={size},Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        f"BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV={margin},MarginL=20,MarginR=20"
    )


def assemble_video(
    scenes: list[SceneMedia],
    output_path: Path,
    *,
    spec: FormatSpec,
    ffmpeg: FFmpeg,
    work_dir: Path,
    music_path: Path | None = None,
    subtitles: bool = True,
) -> ProbeResult:
    if not scenes:
        raise ValueError("Nothing to assemble.")
    work_dir.mkdir(parents=True, exist_ok=True)
    base = [ffmpeg.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error"]
    segments, speech, starts, t = [], [], [], 0.0
    for index, scene in enumerate(scenes):
        voice = ffmpeg.probe(scene.audio).duration_seconds
        duration = max(voice + SCENE_PAUSE, MIN_SCENE)
        frames = round(duration * spec.fps)
        segment = work_dir / f"segment_{index:03d}.mp4"
        if scene.is_video:
            inputs = ["-stream_loop", "-1", "-i", str(scene.visual)]
            vf = _clip_filter(spec, duration)
        else:
            # A single input frame: zoompan itself emits `frames` frames from it.
            inputs = ["-i", str(scene.visual)]
            vf = _shot_filter(spec, frames, index)
        ffmpeg.run(
            [
                *base,
                *inputs,
                "-i",
                str(scene.audio),
                "-filter_complex",
                f"[0:v]{vf}[v];[1:a]aresample=48000,apad,atrim=0:{duration:.3f}[a]",
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-frames:v",
                str(frames),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ac",
                "2",
                str(segment),
            ]
        )
        segments.append(segment)
        speech.append(voice)
        starts.append(t)
        t += frames / spec.fps

    concat_list = work_dir / "segments.txt"
    concat_list.write_text("".join(f"file '{s.name}'\n" for s in segments), encoding="utf-8")
    joined = work_dir / "joined.mp4"
    ffmpeg.run([*base, "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(joined)])

    portrait = spec.height > spec.width
    filters = []
    if subtitles:
        cues = subtitle_cues([s.narration for s in scenes], speech, starts, 4 if portrait else 9)
        srt = write_srt(cues, work_dir / "subtitles.srt")
        filters.append(
            f"[0:v]subtitles=filename={escape_filter_value(str(srt))}:force_style='{subtitle_style(portrait)}'[v]"
        )
    else:
        filters.append("[0:v]null[v]")
    args = [*base, "-i", str(joined)]
    if music_path is not None:
        args += ["-stream_loop", "-1", "-i", str(music_path)]
        # Music at low volume, pushed further down whenever the narrator speaks.
        filters.append(
            "[1:a]volume=0.25[m];[0:a]asplit=2[voice][key];"
            "[m][key]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400[duck];"
            "[voice][duck]amix=inputs=2:normalize=0:duration=first[a]"
        )
    else:
        filters.append("[0:a]anull[a]")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(
        [
            *args,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(output_path),
        ]
    )
    return ffmpeg.probe(output_path)
