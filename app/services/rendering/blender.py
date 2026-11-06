"""Runs the procedural 3D engines (render_engines/) in Blender background mode."""

import shutil
import subprocess
import sys
from pathlib import Path

from app.core.errors import IntegrationNotConfiguredError, RenderError

REPO_ROOT = Path(__file__).resolve().parents[3]
ENGINE_ENTRY = REPO_ROOT / "render_engines" / "run.py"


class Blender:
    def __init__(self, binary: str = "blender", timeout_seconds: float | None = None) -> None:
        self.binary = binary
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def version(self) -> str | None:
        if not self.is_available():
            return None
        out = subprocess.run([self.binary, "--version"], capture_output=True, text=True, check=False)
        return out.stdout.splitlines()[0].strip() if out.stdout else None

    def build_command(
        self,
        spec_path: Path,
        frames_dir: Path,
        *,
        aspect: str,
        quality: str,
        scale: float | None = None,
        samples: int | None = None,
        max_frames: int | None = None,
        threads: int = 0,
        resume: bool = False,
        motion_blur: bool = True,
    ) -> list[str]:
        cmd = [
            self.binary,
            "--background",
            "--factory-startup",
            "-noaudio",
            "--python-exit-code",
            "1",
            "--python",
            str(ENGINE_ENTRY),
            "--",
            "--spec",
            str(spec_path),
            "--aspect",
            aspect,
            "--quality",
            quality,
            "--frames-dir",
            str(frames_dir),
            "--threads",
            str(threads),
        ]
        if scale is not None:
            cmd += ["--scale", str(scale)]
        if samples is not None:
            cmd += ["--samples", str(samples)]
        if max_frames is not None:
            cmd += ["--max-frames", str(max_frames)]
        if resume:
            cmd.append("--resume")
        if not motion_blur:
            cmd.append("--no-motion-blur")
        return cmd

    def render_frames(
        self, spec_path: Path, frames_dir: Path, *, log_path: Path | None = None, **options
    ) -> list[Path]:
        if not self.is_available():
            raise IntegrationNotConfiguredError(
                "Blender not found. Run scripts/install_blender.sh or set BLENDER_BINARY."
            )
        frames_dir.mkdir(parents=True, exist_ok=True)
        if not options.get("resume"):
            for stale in frames_dir.glob("frame_*.png"):
                stale.unlink()
        cmd = self.build_command(spec_path, frames_dir, **options)
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            cmd[1:1] = ["--log-file", str(log_path.resolve())]
        # Inherit stdout/stderr: Blender prints a flushed progress line after every rendered frame.
        try:
            proc = subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr, timeout=self.timeout_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RenderError(
                f"Blender exceeded its {self.timeout_seconds}s render timeout; partial frames were retained."
            ) from exc
        # Blender's placeholder files for unfinished frames are empty: never treat them as frames.
        frames = sorted(f for f in frames_dir.glob("frame_*.png") if f.stat().st_size > 0)
        if proc.returncode != 0 or not frames:
            raise RenderError(
                f"Blender render failed (exit {proc.returncode}); inspect {log_path or 'the Actions log'}."
            )
        return frames
