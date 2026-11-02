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
