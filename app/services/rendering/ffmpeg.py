"""Thin, testable wrapper around the FFmpeg and FFprobe command-line tools.

Commands are built as argument lists (never shell strings) so user-provided
paths cannot inject shell syntax.
"""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import IntegrationNotConfiguredError, RenderError
from app.services.production.formats import FormatSpec


@dataclass(frozen=True)
class SceneInput:
    image_path: Path
    duration_seconds: float


@dataclass(frozen=True)
class ProbeResult:
    duration_seconds: float
    width: int | None
    height: int | None
    has_audio: bool


def _srt_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(captions: list[dict], path: Path) -> Path:
    """captions: [{"start": s, "end": s, "text": str}] -> SubRip file."""
    blocks = [
        f"{i}\n{_srt_time(c['start'])} --> {_srt_time(c['end'])}\n{c['text'].strip()}\n"
        for i, c in enumerate(sorted(captions, key=lambda c: c["start"]), start=1)
    ]
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def subtitle_filter(path: Path, portrait: bool) -> str:
    """libass burn-in. Sizes are relative to libass' 288-line reference height."""
    size, margin = (11, 70) if portrait else (17, 22)
    style = (
        f"FontName=Inter,FontSize={size},Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,"
        f"BorderStyle=1,Outline=1.6,Shadow=0,Alignment=2,MarginV={margin},MarginL=18,MarginR=18"
    )
    return f"subtitles=filename={escape_filter_value(str(path))}:force_style='{style}'"


def escape_filter_value(value: str) -> str:
    """Two-level escaping from the FFmpeg filtergraph docs (option value, then graph)."""
    for ch in ("\\", "'", ":"):
        value = value.replace(ch, "\\" + ch)
    for ch in ("\\", "'", "[", "]", ",", ";"):
        value = value.replace(ch, "\\" + ch)
    return value


class FFmpeg:
    def __init__(self, ffmpeg_binary: str = "ffmpeg", ffprobe_binary: str = "ffprobe") -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.ffprobe_binary = ffprobe_binary

    def is_available(self) -> bool:
        return shutil.which(self.ffmpeg_binary) is not None and shutil.which(self.ffprobe_binary) is not None

    def version(self) -> str | None:
        if not self.is_available():
            return None
        out = subprocess.run([self.ffmpeg_binary, "-version"], capture_output=True, text=True, check=False)
        return out.stdout.splitlines()[0] if out.stdout else None

    def _require(self) -> None:
        if not self.is_available():
            raise IntegrationNotConfiguredError(
                "FFmpeg/FFprobe not found. Install FFmpeg or set FFMPEG_BINARY / FFPROBE_BINARY."
            )

    def run(self, args: list[str], timeout: float | None = None) -> None:
        self._require()
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        if proc.returncode != 0:
            tail = "\n".join(proc.stderr.strip().splitlines()[-10:])
            raise RenderError(f"FFmpeg failed (exit {proc.returncode}): {tail}")

    def build_slideshow_command(
        self,
        scenes: list[SceneInput],
        spec: FormatSpec,
        output_path: Path,
        audio_path: Path | None = None,
    ) -> list[str]:
        """Images (one per scene) -> H.264/AAC MP4 at the format's resolution.

        Each image is scaled to fit and letterboxed so any source aspect ratio
        works for both 9:16 Shorts and 16:9 long-form output.
        """
        if not scenes:
            raise ValueError("At least one scene is required.")
        args = [self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error"]
        for scene in scenes:
            if scene.duration_seconds <= 0:
                raise ValueError("Scene durations must be positive.")
            args += ["-loop", "1", "-t", f"{scene.duration_seconds:.3f}", "-i", str(scene.image_path)]
        if audio_path is not None:
            args += ["-i", str(audio_path)]

        w, h = spec.width, spec.height
        filters = [
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={spec.fps},format=yuv420p[v{i}]"
            for i in range(len(scenes))
        ]
        concat_inputs = "".join(f"[v{i}]" for i in range(len(scenes)))
        filters.append(f"{concat_inputs}concat=n={len(scenes)}:v=1:a=0[vout]")
        args += ["-filter_complex", ";".join(filters), "-map", "[vout]"]

        if audio_path is not None:
            args += ["-map", f"{len(scenes)}:a", "-c:a", "aac", "-b:a", spec.audio_bitrate, "-shortest"]
        args += [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-b:v",
            spec.video_bitrate,
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(spec.fps),
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        return args

    def render_slideshow(
        self,
        scenes: list[SceneInput],
        spec: FormatSpec,
        output_path: Path,
        audio_path: Path | None = None,
    ) -> ProbeResult:
        for scene in scenes:
            if not scene.image_path.is_file():
                raise RenderError(f"Scene image not found: {scene.image_path}")
        if audio_path is not None and not audio_path.is_file():
            raise RenderError(f"Audio file not found: {audio_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.run(self.build_slideshow_command(scenes, spec, output_path, audio_path))
        return self.probe(output_path)

    def concat_clips(self, clips: list[Path], output_path: Path) -> None:
        """Silent clips with the same size and frame rate, one after the other (hard cuts), re-encoded once."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        args = [self.ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error"]
        for clip in clips:
            args += ["-i", str(clip)]
        chain = "".join(f"[{i}:v]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[v]"
        args += [
            "-filter_complex",
            chain,
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(output_path),
        ]
        self.run(args)

    def encode_frames(
        self,
        frames_dir: Path,
        fps: int,
        output_path: Path,
        *,
        audio_path: Path | None = None,
        subtitles_path: Path | None = None,
        portrait: bool = False,
        crf: int = 18,
    ) -> ProbeResult:
        """PNG sequence (frame_0001.png ...) -> H.264 MP4, with optional audio and burned-in subtitles."""
        frame_files = sorted(frames_dir.glob("frame_*.png"))
        if not frame_files:
            raise RenderError(f"No frames found in {frames_dir}")
        # The image sequence defines the authoritative video duration.
        # Trim/pad audio to that exact duration instead of relying on -shortest,
        # whose packet-boundary buffering can extend the MP4 container duration.
        video_duration = len(frame_files) / fps
        output_path.parent.mkdir(parents=True, exist_ok=True)
        args = [
            self.ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(fps),
            "-start_number",
            "1",
            "-i",
            str(frames_dir / "frame_%04d.png"),
        ]
        if audio_path is not None:
            args += ["-i", str(audio_path)]
        if subtitles_path is not None:
            args += ["-vf", subtitle_filter(subtitles_path, portrait)]
        args += ["-map", "0:v"]
        if audio_path is not None:
            # Pad short audio with silence and cut long audio at the end of the video.
            args += [
                "-map",
                "1:a",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-af",
                f"apad,atrim=duration={video_duration:.6f}",
            ]
        args += [
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-t",
            f"{video_duration:.6f}",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        self.run(args)
        return self.probe(output_path)

    def generate_ambient_audio(self, duration_seconds: float, output_path: Path, root_hz: float = 196.0) -> Path:
        """Soft synthesized pad (major chord + filtered noise) with fades. Royalty-free by construction."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        d = f"{duration_seconds:.2f}"
        notes = [root_hz, root_hz * 1.25, root_hz * 1.5, root_hz * 2]
        sources = []
        for f in notes:
            sources += ["-f", "lavfi", "-i", f"sine=frequency={f:.2f}:duration={d}:sample_rate=48000"]
        sources += ["-f", "lavfi", "-i", f"anoisesrc=color=brown:amplitude=0.4:duration={d}:sample_rate=48000"]
        n = len(notes)
        chord = "".join(
            f"[{i}:a]volume={0.16 / (i + 1):.3f},tremolo=f={0.2 + i * 0.07:.2f}:d=0.4[n{i}];" for i in range(n)
        )
        mix = (
            f"{chord}[{n}:a]lowpass=f=500,volume=0.25[noise];"
            + "".join(f"[n{i}]" for i in range(n))
            + f"[noise]amix=inputs={n + 1}:normalize=0,lowpass=f=2500,"
            f"afade=t=in:d=1.0,afade=t=out:st={max(0.0, duration_seconds - 1.5):.2f}:d=1.5[out]"
        )
        self.run(
            [
                self.ffmpeg_binary,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                *sources,
                "-filter_complex",
                mix,
                "-map",
                "[out]",
                "-ac",
                "2",
                str(output_path),
            ]
        )
        return output_path

    def extract_frame(self, video_path: Path, at_seconds: float, output_path: Path) -> Path:
        """Grab one frame, e.g. as a thumbnail starting point."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.run(
            [
                self.ffmpeg_binary,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{at_seconds:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(output_path),
            ]
        )
        return output_path

    def probe(self, path: Path) -> ProbeResult:
        self._require()
        proc = subprocess.run(
            [self.ffprobe_binary, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RenderError(f"FFprobe failed for {path}: {proc.stderr.strip()}")
        info = json.loads(proc.stdout)
        video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
        has_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
        return ProbeResult(
            duration_seconds=float(info.get("format", {}).get("duration", 0.0)),
            width=video.get("width"),
            height=video.get("height"),
            has_audio=has_audio,
        )
