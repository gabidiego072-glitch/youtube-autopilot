"""Natural, free, offline text-to-speech with Kokoro-82M (Apache-2.0) through ONNX Runtime on the CPU.

Much more human than Piper: breathing pauses, intonation, emphasis. Model files (kokoro-v1.0.onnx and
voices-v1.0.bin, ~350 MB) live in KOKORO_MODEL_DIR; scripts/install_kokoro.sh downloads them.
"""

from __future__ import annotations

from pathlib import Path

from app.core.errors import IntegrationNotConfiguredError, ProviderError

MODEL_FILE, VOICES_FILE = "kokoro-v1.0.onnx", "voices-v1.0.bin"
_ENGINES: dict[str, object] = {}


def language_code(voice: str) -> str:
    """Kokoro's phonemizer language for a voice id (ef_/em_ Spanish, b*_ British, a*_ American)."""
    return {"e": "es", "b": "en-gb", "a": "en-us"}.get(voice[:1], "en-us")


class KokoroTTS:
    name = "kokoro"

    def __init__(self, model_dir: Path | None, voice: str, speed: float = 1.05) -> None:
        self.model_dir = Path(model_dir) if model_dir else None
        self.voice = voice
        self.speed = speed

    def is_available(self) -> bool:
        if self.model_dir is None:
            return False
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            return False
        return (self.model_dir / MODEL_FILE).is_file() and (self.model_dir / VOICES_FILE).is_file()

    def _engine(self):
        key = str(self.model_dir)
        if key not in _ENGINES:  # loading the model takes a few seconds: once per process
            from kokoro_onnx import Kokoro

            _ENGINES[key] = Kokoro(str(self.model_dir / MODEL_FILE), str(self.model_dir / VOICES_FILE))
        return _ENGINES[key]

    def synthesize(self, text: str, output_path: Path) -> Path:
        if not self.is_available():
            raise IntegrationNotConfiguredError(
                "Kokoro voice not configured: pip install kokoro-onnx soundfile and run scripts/install_kokoro.sh."
            )
        import soundfile

        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            samples, rate = self._engine().create(
                text, voice=self.voice, speed=self.speed, lang=language_code(self.voice)
            )
        except Exception as exc:  # noqa: BLE001 - report any engine failure as a provider error
            raise ProviderError(f"Kokoro failed: {exc}") from exc
        soundfile.write(str(output_path), samples, rate)
        return output_path
