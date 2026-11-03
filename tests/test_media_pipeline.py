"""Procedural scene planning, Piper voice and the FFmpeg editor (no AI imagery anywhere)."""

import copy
import subprocess
import sys
from pathlib import Path

import pytest

from app.api.deps import provide_blender, provide_tts
from app.core.errors import IntegrationNotConfiguredError, ProviderError
from app.models.enums import VideoFormat
from app.services.editing.assembler import SceneMedia, assemble_video, subtitle_cues
from app.services.production.formats import FormatSpec
from app.services.rendering.ffmpeg import FFmpeg
from app.services.scenes.planner import SYSTEM_PROMPT, finalize, plan_scenes
from app.services.voice.piper import PiperTTS
from render_engines.core.catalog import ACTIONS, PROPS, catalog_text
from render_engines.core.retime import retime
from render_engines.core.spec import build_context, load_spec
from tests.conftest import (
    FACTCHECK_PASS,
    METADATA_RESPONSE,
    SCRIPT_RESPONSE,
    STORYBOARD_RESPONSE,
    StubAIProvider,
    make_settings,
    storyboard_scene,
)
from tests.helpers import create_project

ffmpeg = FFmpeg()
requires_ffmpeg = pytest.mark.skipif(not ffmpeg.is_available(), reason="ffmpeg not installed")
REPO = Path(__file__).resolve().parent.parent
VOICE = REPO / "models" / "voices" / "es_ES-davefx-medium.onnx"
PIPER = str(Path(sys.executable).parent / "piper")  # installed in the venv by piper-tts
TINY = FormatSpec(VideoFormat.SHORT, 180, 320, 24, 1, None, "1M", "96k")


def test_catalog_lists_engine_features():
    text = catalog_text()
    assert "planet" in PROPS and "spin" in ACTIONS and "grow" in ACTIONS
    assert "space" in text and "meadow" in text


def test_storyboard_prompt_is_procedural_only():
    assert "procedural 3D engine" in SYSTEM_PROMPT and "no AI images" in SYSTEM_PROMPT
    assert "hyper" not in SYSTEM_PROMPT.lower().replace("no hyper-realism", "")


def test_retime_scales_every_time():
    spec = load_spec(REPO / "examples" / "scenes" / "what_if_earth_stops.json")
    longer = retime(spec, 16)
    assert longer["duration_seconds"] == 16
    assert longer["actions"][0]["start"] == spec["actions"][0]["start"] * 2
    assert [s["time"] for s in longer["camera"]["shots"]] == [s["time"] * 2 for s in spec["camera"]["shots"]]
    assert longer["captions"][-1]["end"] <= 16
    assert spec["duration_seconds"] == 8  # original untouched


def test_finalize_fills_engine_fields_and_clamps():
    raw = copy.deepcopy(storyboard_scene(0))
    raw["camera"]["shots"][1]["time"] = 99
    raw["camera"]["shots"].append({"time": 0.5, "location": [0, -4, 1], "target_point": [1, 2, 3], "lens": 30})
    raw["props"] = [{"id": "earth", "type": "planet", "location": [0, 0], "radius": 2}]
    spec = finalize(raw, duration=2.5, seed=7, palette={"body": "#112233"})
    assert spec["engine"] == "cinematic" and spec["seed"] == 7 and spec["captions"] == []
    assert [s["time"] for s in spec["camera"]["shots"]] == [0.0, 0.5, 2.5]
    assert spec["camera"]["shots"][1]["target"] == [1, 2, 3]
    assert spec["props"][0]["location"] == [0, 0, 0.0]
    assert spec["characters"][0]["palette"] == {"body": "#112233"}


def test_plan_scenes_validates_against_engine():
    durations = [2.0] * len(SCRIPT_RESPONSE["scenes"])
    specs = plan_scenes(
        StubAIProvider([STORYBOARD_RESPONSE]),
        scenes=SCRIPT_RESPONSE["scenes"],
        durations=durations,
        visual_bible=SCRIPT_RESPONSE["visual_bible"],
        seed=3,
    )
    assert len(specs) == len(durations) and all(s["duration_seconds"] == 2.0 for s in specs)

    bad = copy.deepcopy(STORYBOARD_RESPONSE)
    bad["scenes"][2]["actions"][0]["character"] = "ghost"
    with pytest.raises(ProviderError, match="scene 2"):
        plan_scenes(
            StubAIProvider([bad]), scenes=SCRIPT_RESPONSE["scenes"], durations=durations, visual_bible=None, seed=3
        )
    with pytest.raises(ProviderError, match="Storyboard has 1 scenes"):
        plan_scenes(
            StubAIProvider([{"scenes": bad["scenes"][:1]}]),
            scenes=SCRIPT_RESPONSE["scenes"],
            durations=durations,
            visual_bible=None,
            seed=3,
        )


def test_piper_not_configured(tmp_path):
    with pytest.raises(IntegrationNotConfiguredError):
        PiperTTS("piper", None).synthesize("hola", tmp_path / "x.wav")
    assert PiperTTS("piper", Path("v.onnx"), 0.9).command(Path("o.wav"))[-2:] == ["--length-scale", "0.9"]


@pytest.mark.skipif(not PiperTTS(PIPER, VOICE).is_available(), reason="Piper voice not installed")
def test_piper_real_spanish_voice(tmp_path):
    out = PiperTTS(PIPER, VOICE).synthesize("¿Qué pasaría si la gravedad se duplicase?", tmp_path / "v.wav")
    assert ffmpeg.probe(out).duration_seconds > 1.0


def test_subtitle_cues_follow_speech():
    cues = subtitle_cues(["uno dos tres cuatro cinco", "seis"], [2.0, 1.0], [0.0, 2.5], 4)
    assert [c["text"] for c in cues] == ["uno dos tres cuatro", "cinco", "seis"]
    assert cues[1]["start"] == 1.6 and cues[2]["start"] == 2.5


def _tone(path: Path, seconds: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=f=300:d={seconds}", str(path)], check=True
    )
    return path


def _clip(path: Path, seconds: float) -> Path:
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=s=320x240:d={seconds}", str(path)],
        check=True,
    )
    return path


@requires_ffmpeg
def test_assemble_real_video(tmp_path):
    scenes = [
        SceneMedia(
            _clip(tmp_path / "a.mp4", 1.5), _tone(tmp_path / "a.wav", 1.0), "¿Y si la Tierra se parase?", is_video=True
        ),
        SceneMedia(
            _clip(tmp_path / "b.mp4", 0.5), _tone(tmp_path / "b.wav", 1.5), "Todo saldría volando.", is_video=True
        ),  # shorter clip than its voice: it loops
    ]
    music = _tone(tmp_path / "m.wav", 0.7)
    result = assemble_video(
        scenes, tmp_path / "out.mp4", spec=TINY, ffmpeg=ffmpeg, work_dir=tmp_path / "w", music_path=music
    )
    assert (result.width, result.height) == (180, 320) and result.has_audio
    assert 2.8 <= result.duration_seconds <= 3.3  # 1.0 + 1.5 + 2 x 0.25 pause
    assert "¿Y si la" in (tmp_path / "w" / "subtitles.srt").read_text()


class _StubVoice:
    name = "stub-voice"

    def synthesize(self, text, output_path):
        return _tone(output_path, 0.4)


class _StubBlender:
    """Writes test-pattern frames instead of running Blender (real renders: test_render_pipeline.py)."""

    def __init__(self):
        self.specs = []

    def is_available(self):
        return True

    def render_frames(
        self,
        spec_path,
        frames_dir,
        *,
        log_path=None,
        aspect,
        quality,
        scale=None,
        samples=None,
        max_frames=None,
        threads=0,
    ):
        spec = load_spec(spec_path)
        self.specs.append(spec)
        ctx = build_context(spec, aspect, "test", scale=0.1)
        frames_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc=s={ctx.width}x{ctx.height}:r={ctx.fps}",
                "-frames:v",
                str(ctx.frame_count),
                "-start_number",
                "1",
                str(frames_dir / "frame_%04d.png"),
            ],
            check=True,
        )
        return sorted(frames_dir.glob("frame_*.png"))


@requires_ffmpeg
def test_full_production_api(make_client, channel, tmp_path):
    """script -> fact-check -> voice -> storyboard -> 3D render job -> edit -> metadata -> approve."""
    settings = make_settings(media_root=tmp_path / "media", edit_resolution_scale=0.12)
    client = make_client(
        settings, ai=StubAIProvider([SCRIPT_RESPONSE, FACTCHECK_PASS, STORYBOARD_RESPONSE, METADATA_RESPONSE])
    )
    blender = _StubBlender()
    client.app.dependency_overrides[provide_tts] = lambda: _StubVoice()
    client.app.dependency_overrides[provide_blender] = lambda: blender
    pid = create_project(client, channel["id"])["id"]

    script = client.post(f"/api/v1/projects/{pid}/scripts/generate").json()
    client.post(f"/api/v1/projects/{pid}/scripts/{script['id']}/fact-check")
    assert client.post(f"/api/v1/projects/{pid}/scenes/plan").status_code == 409  # voice first
    assert client.post(f"/api/v1/projects/{pid}/scenes/render", json={}).status_code == 409  # plan first

    voice = client.post(f"/api/v1/projects/{pid}/voice/generate")
    assert voice.status_code == 201 and len(voice.json()) == len(script["scenes"])
    planned = client.post(f"/api/v1/projects/{pid}/scenes/plan")
    assert planned.status_code == 200, planned.text
    specs = planned.json()["scene_specs"]
    assert len(specs) == len(script["scenes"])
    assert specs[0]["duration_seconds"] == 1.0  # 0.4 s voice + pause, never shorter than 1 s

    job = client.post(f"/api/v1/projects/{pid}/scenes/render", json={"quality": "test"})
    assert job.status_code == 202, job.text
    finished = client.get(f"/api/v1/renders/{job.json()['id']}").json()  # background task already ran
    assert finished["status"] == "succeeded", finished["error"]
    assert len(blender.specs) == len(script["scenes"])
    assert all(s["engine"] == "cinematic" for s in blender.specs)

    final = client.post(f"/api/v1/projects/{pid}/assemble", json={})
    assert final.status_code == 201, final.text
    assert final.json()["status"] == "succeeded" and Path(final.json()["output_path"]).is_file()
    assert client.get(f"/api/v1/projects/{pid}").json()["status"] == "rendered"

    client.post(f"/api/v1/projects/{pid}/metadata/generate")
    approved = client.post(f"/api/v1/projects/{pid}/approve")
    assert approved.status_code == 200, approved.text
    kinds = [a["kind"] for a in client.get(f"/api/v1/projects/{pid}/assets").json()]
    assert kinds.count("video_clip") == len(script["scenes"]) and kinds.count("render_output") == 1


def test_scene_render_reports_missing_blender(make_client, channel):
    class _NoBlender(_StubBlender):
        def is_available(self):
            return False

    client = make_client(ai=StubAIProvider([SCRIPT_RESPONSE]))
    client.app.dependency_overrides[provide_blender] = lambda: _NoBlender()
    pid = create_project(client, channel["id"])["id"]
    client.post(f"/api/v1/projects/{pid}/scripts/generate")
    assert client.post(f"/api/v1/projects/{pid}/scenes/render", json={}).status_code == 409  # not planned yet
