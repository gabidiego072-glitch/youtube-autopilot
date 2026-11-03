"""3D pipeline: FFmpeg post-processing (always) and real Blender renders (when installed)."""

import subprocess
from pathlib import Path

import pytest

from app.services.rendering.blender import ENGINE_ENTRY, Blender
from app.services.rendering.ffmpeg import FFmpeg, escape_filter_value, write_srt
from app.services.rendering.scene3d import render_scene_video

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "scenes"
ffmpeg = FFmpeg()
blender = Blender()
requires_ffmpeg = pytest.mark.skipif(not ffmpeg.is_available(), reason="ffmpeg not installed")
requires_blender = pytest.mark.skipif(not blender.is_available(), reason="blender not installed")


def test_srt_writer(tmp_path):
    path = write_srt(
        [{"start": 61.5, "end": 63.25, "text": " Hi "}, {"start": 0, "end": 1, "text": "First"}], tmp_path / "c.srt"
    )
    assert path.read_text().splitlines()[:3] == ["1", "00:00:00,000 --> 00:00:01,000", "First"]
    assert "00:01:01,500 --> 00:01:03,250" in path.read_text()


def test_filter_escaping():
    assert escape_filter_value("/tmp/a:b,c.srt") == "/tmp/a\\\\:b\\,c.srt"


def test_blender_command():
    cmd = Blender("blender").build_command(Path("s.json"), Path("f"), aspect="9:16", quality="draft", max_frames=3)
    assert cmd[:3] == ["blender", "--background", "--factory-startup"]
    assert str(ENGINE_ENTRY) in cmd and cmd[cmd.index("--aspect") + 1] == "9:16"
    assert cmd[cmd.index("--max-frames") + 1] == "3"


@requires_ffmpeg
def test_encode_frames_with_audio_and_subtitles(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=180x320:rate=24",
            "-frames:v",
            "24",
            "-start_number",
            "1",
            str(frames / "frame_%04d.png"),
        ],
        check=True,
    )
    audio = ffmpeg.generate_ambient_audio(3.0, tmp_path / "amb.wav")
    tricky = tmp_path / "it's a:b,c"  # characters that need filtergraph escaping
    tricky.mkdir()
    srt = write_srt([{"start": 0.1, "end": 0.9, "text": "Hello"}], tricky / "c.srt")
    result = ffmpeg.encode_frames(frames, 24, tmp_path / "out.mp4", audio_path=audio, subtitles_path=srt, portrait=True)
    assert (result.width, result.height) == (180, 320)
    assert result.has_audio
    assert 0.9 <= result.duration_seconds <= 1.15  # audio is cut to the video length


@requires_ffmpeg
def test_encode_requires_frames(tmp_path):
    from app.core.errors import RenderError

    with pytest.raises(RenderError):
        ffmpeg.encode_frames(tmp_path, 24, tmp_path / "x.mp4")


def test_missing_blender_is_reported(tmp_path):
    from app.core.errors import IntegrationNotConfiguredError

    with pytest.raises(IntegrationNotConfiguredError):
        Blender("definitely-not-blender").render_frames(
            EXAMPLES / "what_if_grow_each_step.json", tmp_path, aspect="16:9", quality="test"
        )


@requires_blender
@requires_ffmpeg
@pytest.mark.parametrize(
    ("spec", "aspect"),
    [
        ("what_if_grow_each_step.json", "16:9"),
        ("what_if_grow_each_step.json", "9:16"),
        ("what_if_earth_stops.json", "9:16"),
    ],
)
def test_real_blender_render_to_mp4(tmp_path, spec, aspect):
    """Builds the full scene in Blender and renders a few tiny frames, then encodes them."""
    result = render_scene_video(
        EXAMPLES / spec,
        tmp_path / "out.mp4",
        blender=blender,
        ffmpeg=ffmpeg,
        aspect=aspect,
        quality="test",
        scale=0.08,
        samples=1,
        max_frames=4,
        ambient_audio=True,
        threads=2,
    )
    expected = (152, 86) if aspect == "16:9" else (86, 152)
    assert (result.probe.width, result.probe.height) == expected
    assert result.frame_count == 4 and len(list(result.frames_dir.glob("frame_*.png"))) == 4
    assert result.probe.has_audio
    assert result.video_path.stat().st_size > 1000


@requires_blender
@pytest.mark.parametrize("index", [2, 3, 5, 7])  # fling + wind, arrows + labels, sun path, magnetic field
def test_first_short_scenes_render(tmp_path, index):
    """The new explanatory elements of the first Short build and render in real Blender."""
    import json as _json

    production = _json.loads(
        (
            EXAMPLES.parent.parent / "productions" / "archive" / "what_if_earth_stops_v1_planet" / "production.json"
        ).read_text()
    )
    spec = {"engine": "cinematic", "fps": 24, "seed": 5, **production["scenes"][index]}
    path = tmp_path / "scene.json"
    path.write_text(_json.dumps(spec))
    result = render_scene_video(
        path,
        tmp_path / "out.mp4",
        blender=blender,
        ffmpeg=ffmpeg,
        aspect="9:16",
        quality="test",
        scale=0.08,
        samples=1,
        max_frames=3,
        threads=2,
        subtitles=False,
    )
    assert result.frame_count == 3 and result.video_path.stat().st_size > 500


@requires_blender
@pytest.mark.parametrize("name", ["street_sudden_stop", "home_sudden_stop", "coast_surge"])
def test_urban_environments_render_with_physics(tmp_path, name):
    """City street, home interior and seafront (with rigid-body physics) build and render in real Blender."""
    result = render_scene_video(EXAMPLES / "urban" / f"{name}.json", tmp_path / "out.mp4", blender=blender,
                                ffmpeg=ffmpeg, aspect="9:16", quality="test", scale=0.08, samples=1, max_frames=3,
                                threads=2, subtitles=False)
    assert result.frame_count == 3 and result.video_path.stat().st_size > 500
