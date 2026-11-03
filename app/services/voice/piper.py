"""Free, offline text-to-speech with Piper (https://github.com/OHF-Voice/piper1-gpl)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from app.core.errors import IntegrationNotConfiguredError, ProviderError


class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, output_path: Path) -> Path: ...


class PiperTTS:
    name = "piper"

    def __init__(self, binary: str, model_path: Path | None, length_scale: float = 1.0) -> None:
        self.binary = binary
        self.model_path = model_path
        self.length_scale = length_scale

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None and self.model_path is not None and self.model_path.is_file()

    def command(self, output_path: Path) -> list[str]:
        return [
            self.binary,
            "-m",
            str(self.model_path),
            "-f",
            str(output_path),
            "--length-scale",
            str(self.length_scale),
        ]

    def synthesize(self, text: str, output_path: Path) -> Path:
        if not self.is_available():
            raise IntegrationNotConfiguredError(
                "Piper voice not configured. pip install piper-tts, run scripts/install_voice.sh and set "
                "PIPER_VOICE_MODEL."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(self.command(output_path), input=text, capture_output=True, text=True, check=False)
        if proc.returncode != 0 or not output_path.is_file():
            raise ProviderError(f"Piper failed: {proc.stderr.strip()[-500:]}")
        return output_path
