import subprocess
from pathlib import Path

import pytest

from app.core.errors import IntegrationNotConfiguredError, RenderError
from app.models.enums import VideoFormat
from app.services.production.formats import get_format_spec
from app.services.rendering.ffmpeg import FFmpeg, SceneInput
from tests.conftest import make_settings

ffmpeg = FFmpeg()
requires_ffmpeg = pytest.mark.skipif(not ffmpeg.is_available(), reason="ffmpeg not installed")
SETTINGS = make_settings()


def test_command_builder_short(tmp_path):
    spec = get_format_spec(VideoFormat.SHORT, SETTINGS)
    scenes = [SceneInput(tmp_path / "a.png", 2), SceneInput(tmp_path / "b.png", 1.5)]
    cmd = ffmpeg.build_slideshow_command(scenes, spec, tmp_path / "out.mp4", audio_path=tmp_path / "vo.wav")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "scale=1080:1920" in graph and "concat=n=2" in graph
    assert cmd[cmd.index("-map", cmd.index("[vout]")) + 1] == "2:a"
    assert "-shortest" in cmd and cmd[-1].endswith("out.mp4")


def test_command_builder_rejects_bad_input(tmp_path):
    spec = get_format_spec(VideoFormat.LONG, SETTINGS)
    with pytest.raises(ValueError):
        ffmpeg.build_slideshow_command([], spec, tmp_path / "o.mp4")
    with pytest.raises(ValueError):
        ffmpeg.build_slideshow_command([SceneInput(tmp_path / "a.png", 0)], spec, tmp_path / "o.mp4")


def test_missing_binary_is_reported():
    missing = FFmpeg("definitely-not-ffmpeg", "definitely-not-ffprobe")
    assert missing.version() is None
    with pytest.raises(IntegrationNotConfiguredError):
        missing.probe(Path("x.mp4"))


def _make_image(path: Path, color: str, size: str) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={size}",
            "-frames:v",
            "1",
            str(path),
        ],
        check=True,
    )
    return path


def _make_tone(path: Path, seconds: float) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            str(path),
        ],
        check=True,
    )
    return path


@requires_ffmpeg
@pytest.mark.parametrize(
    ("video_format", "dims"), [(VideoFormat.SHORT, (1080, 1920)), (VideoFormat.LONG, (1920, 1080))]
)
def test_real_render_produces_correct_format(tmp_path, video_format, dims):
    spec = get_format_spec(video_format, SETTINGS)
    scenes = [
        SceneInput(_make_image(tmp_path / "red.png", "red", "640x480"), 1.0),
        SceneInput(_make_image(tmp_path / "blue.png", "blue", "480x640"), 1.0),
    ]
    audio = _make_tone(tmp_path / "tone.wav", 2.0)
    result = ffmpeg.render_slideshow(scenes, spec, tmp_path / "out" / "video.mp4", audio_path=audio)
    assert (result.width, result.height) == dims
    assert result.has_audio
    assert 1.8 <= result.duration_seconds <= 2.3

    frame = ffmpeg.extract_frame(tmp_path / "out" / "video.mp4", 0.5, tmp_path / "thumb.jpg")
    assert frame.stat().st_size > 0


@requires_ffmpeg
def test_render_reports_missing_inputs(tmp_path):
    spec = get_format_spec(VideoFormat.SHORT, SETTINGS)
    with pytest.raises(RenderError, match="not found"):
        ffmpeg.render_slideshow([SceneInput(tmp_path / "nope.png", 1)], spec, tmp_path / "o.mp4")
