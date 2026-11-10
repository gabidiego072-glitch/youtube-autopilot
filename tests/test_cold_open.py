"""The video opens on its most striking moment with the title, then the story; first-person sounds exist."""

import shutil
import subprocess

import pytest

from app.models.enums import VideoFormat
from app.services.audio.synth import SFX, generate_sfx
from app.services.editing.assembler import ColdOpen, EditScene, assemble_video, plan_timeline
from app.services.production.formats import FormatSpec
from app.services.production.short import cold_open_scene
from app.services.rendering.ffmpeg import FFmpeg

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_the_opening_is_the_most_striking_scene_but_never_the_first():
    specs = [
        {"recipe": "street_run", "environment": {"chasers": 20}, "actions": []},
        {"recipe": "kitchen", "environment": {}, "actions": []},
        {"recipe": "street_watch", "environment": {}, "actions": [{"type": "collapse"}]},
        {"recipe": "street_run", "environment": {"chasers": 20}, "actions": [{"type": "fall"}]},
    ]
    assert cold_open_scene(specs, [0, 1, 2, 3]) == 3
    assert cold_open_scene([{"environment": {}, "actions": []}] * 3, [0, 1, 2]) is None


def test_first_person_sounds_are_known():
    assert {"heartbeat", "breath", "steps"} <= set(SFX)


@needs_ffmpeg
def test_cold_open_comes_first_and_shifts_the_story(tmp_path):
    ffmpeg = FFmpeg("ffmpeg", "ffprobe")
    clips, voices = [], []
    for i, colour in enumerate(("red", "green", "blue")):
        clip, voice = tmp_path / f"c{i}.mp4", tmp_path / f"v{i}.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color={colour}:s=270x480:d=3:r=24",
                "-pix_fmt",
                "yuv420p",
                str(clip),
            ],
            check=True,
        )
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=400:d=1.5", str(voice)], check=True
        )
        clips.append(clip)
        voices.append(voice)
    slots = plan_timeline([1.5, 1.5, 1.5], ["fade", "flash", "fade"], fps=24)
    beat = generate_sfx(ffmpeg, "heartbeat", tmp_path / "heartbeat.wav")
    scenes = [
        EditScene(clips[i], voices[i], "hola", 1.5, slots[i], [(beat, "heartbeat", 0.1)], "DÍA 1/7") for i in range(3)
    ]
    opening = ColdOpen(clips[2], 0.5, 1.6, "¿Y si todos fueran zombis?", [(beat, "heartbeat", 0.0)])
    spec = FormatSpec(VideoFormat.SHORT, 270, 480, 24, 1, None, "", "")
    probe = assemble_video(
        scenes, tmp_path / "out.mp4", spec=spec, ffmpeg=ffmpeg, work_dir=tmp_path / "edit", cold_open=opening
    )
    story = slots[-1].start + slots[-1].duration
    assert abs(probe.duration_seconds - (story + 1.6)) < 0.15 and probe.has_audio
    assert (tmp_path / "edit" / "title.ass").read_text(encoding="utf-8").count("zombis") == 1


@needs_ffmpeg
def test_qa_accepts_subtitles_shifted_by_the_opening(tmp_path):
    import json

    from app.services.qa.video import check_video

    test_cold_open_comes_first_and_shifts_the_story(tmp_path)
    slots = plan_timeline([1.5, 1.5, 1.5], ["fade", "flash", "fade"], fps=24)
    report = {
        "lead_seconds": 1.6,
        "scenes": [{"start": s.start, "duration": s.duration, "voice_seconds": 1.5} for s in slots],
    }
    (tmp_path / "out.report.json").write_text(json.dumps(report))
    result = check_video(
        tmp_path / "out.mp4",
        frames=2,
        report_path=tmp_path / "out.report.json",
        srt=tmp_path / "edit" / "subtitles.srt",
    )
    assert not any("subtitle" in p for p in result["problems"]), result["problems"]


def test_the_title_number_stands_out_like_the_hand_made_cards():
    from app.services.editing.assembler import _highlight_numbers

    out = _highlight_numbers("subiera 100 metros?")
    assert "100 METROS?" in out and "&HFFB01E&" in out and out.startswith("subiera ")
    assert _highlight_numbers("sin números") == "sin números"


def test_pov_scripts_are_written_like_the_hand_made_videos():
    from app.services.styles import pov_script_note

    note = pov_script_note("en")
    assert "ONE LINE = ONE THING YOU SEE" in note and "+30 m" in note and "DAY 1/N" in note
