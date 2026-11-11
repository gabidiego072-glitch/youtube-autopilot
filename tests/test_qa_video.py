"""Video QA uses the FFmpeg/FFprobe the app is configured with, and reports every command that fails."""

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from app.services.qa.video import QAError, check_video

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe not installed")


@pytest.fixture
def video(tmp_path) -> Path:
    out = tmp_path / "clip.mp4"
    subprocess.run(
        [
            FFMPEG,
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=24:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-shortest",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ],
        check=True,
    )
    return out


def _wrapper(folder: Path, name: str, real: str, fail_when: str | None = None) -> str:
    """An executable with another name (not on the PATH as ffmpeg/ffprobe) that runs the real tool, and fails
    when its arguments contain `fail_when`."""
    path = folder / name
    guard = f'case "$*" in *{fail_when}*) echo "boom: {fail_when}" >&2; exit 3;; esac\n' if fail_when else ""
    path.write_text(f'#!/bin/sh\n{guard}exec "{real}" "$@"\n')
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def test_configured_executables_are_used(video, tmp_path, monkeypatch):
    tools = tmp_path / "tools"
    tools.mkdir()
    ffmpeg = _wrapper(tools, "my-ffmpeg", FFMPEG)
    ffprobe = _wrapper(tools, "my-ffprobe", FFPROBE)
    monkeypatch.setenv("PATH", str(tools))  # no 'ffmpeg' or 'ffprobe' on the PATH at all
    assert shutil.which("ffmpeg") is None
    result = check_video(video, frames=2, ffmpeg=ffmpeg, ffprobe=ffprobe)
    assert result["analysis_errors"] == [] and result["contact_sheet"] and Path(result["contact_sheet"]).is_file()
    assert result["duration_seconds"] == pytest.approx(2.0, abs=0.1)


def test_a_failed_contact_sheet_is_a_qa_problem(video, tmp_path):
    ffmpeg = _wrapper(tmp_path, "ffmpeg-no-sheet", FFMPEG, fail_when="tile=")
    result = check_video(video, frames=2, ffmpeg=ffmpeg, ffprobe=FFPROBE)
    assert not result["passed"] and result["contact_sheet"] is None
    assert any("contact sheet failed (exit 3)" in p and "boom" in p for p in result["problems"])


def test_a_failed_analysis_is_a_qa_problem(video, tmp_path):
    ffmpeg = _wrapper(tmp_path, "ffmpeg-no-loudness", FFMPEG, fail_when="ebur128")
    result = check_video(video, frames=2, ffmpeg=ffmpeg, ffprobe=FFPROBE)
    assert not result["passed"] and result["loudness_lufs"] is None
    assert any(p.startswith("loudness analysis failed (exit 3)") for p in result["problems"])


def test_a_missing_executable_is_reported(video, tmp_path):
    result = check_video(video, frames=2, ffmpeg=str(tmp_path / "nope"), ffprobe=FFPROBE)
    assert not result["passed"] and any("executable not found" in p for p in result["problems"])
    with pytest.raises(QAError, match="ffprobe could not read"):
        check_video(video, frames=2, ffmpeg=FFMPEG, ffprobe=str(tmp_path / "nope"))
    with pytest.raises(QAError, match="exit"):
        broken = tmp_path / "broken.mp4"
        broken.write_bytes(b"not a video")
        check_video(broken, frames=2, ffmpeg=FFMPEG, ffprobe=FFPROBE)


def test_washed_out_and_flat_frames_are_reported(tmp_path):
    """The water video (Nov 11) opened on 3 s of pale sky and empty promenade after the title."""
    clip = tmp_path / "washed.mp4"
    subprocess.run(
        [
            FFMPEG,
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=24:duration=1",
            "-f",
            "lavfi",
            "-i",
            "color=c=0xd8dce0:size=320x240:rate=24:duration=2.5",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=24:duration=1",
            "-filter_complex",
            "[0][1][2]concat=n=3:v=1:a=0,noise=alls=6:allf=t",
            "-pix_fmt",
            "yuv420p",
            str(clip),
        ],
        check=True,
    )
    result = check_video(clip, frames=2, ffmpeg=FFMPEG, ffprobe=FFPROBE)
    assert result["flat_segments"] and result["flat_segments"][0][0] <= 1.5
    assert any("washed-out" in p for p in result["problems"])


def test_a_colourful_bright_scene_is_not_washed_out(video):
    result = check_video(video, frames=2, ffmpeg=FFMPEG, ffprobe=FFPROBE)
    assert result["flat_segments"] == []
