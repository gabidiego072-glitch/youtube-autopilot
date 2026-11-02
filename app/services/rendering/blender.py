"""Runs the procedural 3D engines (render_engines/) in Blender background mode."""

import shutil
import subprocess
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
        return cmd

    def render_frames(
        self, spec_path: Path, frames_dir: Path, *, log_path: Path | None = None, **options
    ) -> list[Path]:
        if not self.is_available():
            raise IntegrationNotConfiguredError(
                "Blender not found. Run scripts/install_blender.sh or set BLENDER_BINARY."
            )
        frames_dir.mkdir(parents=True, exist_ok=True)
        for stale in frames_dir.glob("frame_*.png"):
            stale.unlink()
        cmd = self.build_command(spec_path, frames_dir, **options)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout_seconds, check=False)
        if log_path is not None:
            log_path.write_text(proc.stdout + proc.stderr, encoding="utf-8")
        frames = sorted(frames_dir.glob("frame_*.png"))
        if proc.returncode != 0 or not frames:
            tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-15:])
            raise RenderError(f"Blender render failed (exit {proc.returncode}): {tail}")
        return frames
