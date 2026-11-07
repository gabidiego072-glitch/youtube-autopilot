"""Procedural scene planning, Piper voice and the FFmpeg editor (no AI imagery anywhere)."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.api.deps import provide_blender, provide_tts
from app.core.errors import IntegrationNotConfiguredError, ProviderError
from app.models.enums import VideoFormat
from app.services.editing.assembler import EditScene, assemble_video, plan_timeline, subtitle_cues
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
            StubAIProvider([bad, bad]), scenes=SCRIPT_RESPONSE["scenes"], durations=durations, visual_bible=None, seed=3
        )
    with pytest.raises(ProviderError, match="Storyboard has 1 scenes"):
        plan_scenes(
            StubAIProvider([{"scenes": bad["scenes"][:1]}] * 2),
            scenes=SCRIPT_RESPONSE["scenes"],
            durations=durations,
            visual_bible=None,
            seed=3,
        )


def test_plan_scenes_repairs_references_and_retries_once():
    durations = [2.0] * len(SCRIPT_RESPONSE["scenes"])
    # Coordinate written as an id (seen in a real run): the action is dropped, the storyboard survives.
    slip = copy.deepcopy(STORYBOARD_RESPONSE)
    slip["scenes"][2]["actions"][0]["character"] = "[0, 3, 1]"
    slip["scenes"][1]["camera"]["shots"][0]["target"] = "[0, 5, 1]"
    specs = plan_scenes(
        StubAIProvider([slip]), scenes=SCRIPT_RESPONSE["scenes"], durations=durations, visual_bible=None, seed=3
    )
    assert specs[1]["camera"]["shots"][0]["target"] == [0.0, 5.0, 1.0]
    assert len(specs[2]["actions"]) == len(STORYBOARD_RESPONSE["scenes"][2]["actions"]) - 1

    # A real mistake gets one retry with the reasons in the prompt.
    bad = copy.deepcopy(STORYBOARD_RESPONSE)
    bad["scenes"][2]["actions"][0]["character"] = "ghost"
    stub = StubAIProvider([bad, STORYBOARD_RESPONSE])
    plan_scenes(stub, scenes=SCRIPT_RESPONSE["scenes"], durations=durations, visual_bible=None, seed=3)
    assert len(stub.calls) == 2 and "ghost" in stub.calls[1]["prompt"]


def test_piper_not_configured(tmp_path):
    with pytest.raises(IntegrationNotConfiguredError):
        PiperTTS("piper", None).synthesize("hola", tmp_path / "x.wav")
    assert PiperTTS("piper", Path("v.onnx"), 0.9).command(Path("o.wav"))[-2:] == ["--length-scale", "0.9"]


@pytest.mark.skipif(not PiperTTS(PIPER, VOICE).is_available(), reason="Piper voice not installed")
def test_piper_real_spanish_voice(tmp_path):
    out = PiperTTS(PIPER, VOICE).synthesize("¿Qué pasaría si la gravedad se duplicase?", tmp_path / "v.wav")
    assert ffmpeg.probe(out).duration_seconds > 1.0


def test_timeline_follows_voice_and_absorbs_transitions():
    slots = plan_timeline([1.7, 5.2, 4.0], ["cut", "fade", "cut"], fps=24)
    assert slots[0].start == 0 and slots[0].transition_in == "cut"
    assert abs(slots[1].start - slots[0].duration) < 1e-3  # scenes are back to back
    assert slots[0].clip_length > slots[0].duration  # rendered longer to cover the dissolve into scene 1
    assert abs(slots[1].clip_length - slots[1].duration - 1 / 24) < 1e-3  # a cut is a one-frame dissolve
    assert slots[-1].clip_length == slots[-1].duration
    for slot in slots:
        assert abs(slot.duration * 24 - round(slot.duration * 24)) < 1e-2  # whole frames


def _slot(start, duration):
    return plan_timeline([duration - 0.36], ["cut"], fps=24)[0].__class__(start, duration, duration, "cut", 0.0)


def test_subtitle_cues_follow_speech():
    scenes = [
        EditScene(Path("a"), Path("a"), "uno dos tres cuatro cinco", 2.0, _slot(0.0, 2.5)),
        EditScene(Path("b"), Path("b"), "seis", 1.0, _slot(2.5, 1.5)),
    ]
    cues = subtitle_cues(scenes, 4)
    assert [c["text"] for c in cues] == ["uno dos tres cuatro", "cinco", "seis"]
    assert cues[0]["start"] == 0.06 and cues[-1]["start"] == 2.56
    assert cues[1]["end"] <= 2.06 + 1e-6  # never runs past the voice


def _tone(path: Path, seconds: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=f=300:d={seconds}", str(path)], check=True
    )
    return path


def _clip(path: Path, seconds: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=s=320x240:d={seconds}", str(path)],
        check=True,
    )
    return path


@requires_ffmpeg
def test_synthesised_sound_effects_and_music(tmp_path):
    from app.services.audio.synth import SFX, generate_music, generate_sfx

    for kind in SFX:
        assert ffmpeg.probe(generate_sfx(ffmpeg, kind, tmp_path / f"{kind}.wav")).duration_seconds > 0.5
    assert 9.5 <= ffmpeg.probe(generate_music(ffmpeg, 10, tmp_path / "m.wav")).duration_seconds <= 10.5
    with pytest.raises(ValueError):
        generate_sfx(ffmpeg, "laser", tmp_path / "x.wav")


@requires_ffmpeg
def test_assemble_real_video(tmp_path):
    from app.services.audio.synth import generate_sfx

    speech = [1.0, 1.5]
    slots = plan_timeline(speech, ["cut", "fade"], fps=24)
    boom = generate_sfx(ffmpeg, "impact", tmp_path / "impact.wav")
    scenes = [
        EditScene(
            _clip(tmp_path / "a.mp4", slots[0].clip_length),
            _tone(tmp_path / "a.wav", 1.0),
            "¿Y si la Tierra se parase?",
            1.0,
            slots[0],
            [(boom, "impact", 0.5)],
        ),
        EditScene(
            _clip(tmp_path / "b.mp4", 0.5), _tone(tmp_path / "b.wav", 1.5), "Todo saldría volando.", 1.5, slots[1]
        ),  # clip shorter than its slot: the last frame is held
    ]
    music = _tone(tmp_path / "m.wav", 4.0)
    result = assemble_video(
        scenes, tmp_path / "out.mp4", spec=TINY, ffmpeg=ffmpeg, work_dir=tmp_path / "w", music_path=music
    )
    total = slots[-1].start + slots[-1].duration
    assert (result.width, result.height) == (180, 320) and result.has_audio
    assert abs(result.duration_seconds - total) < 0.1
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
    settings = make_settings(media_root=tmp_path / "media")
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
    assert specs[0]["duration_seconds"] == 1.0  # planned length: 0.4 s voice + pause, at least 1 s

    job = client.post(f"/api/v1/projects/{pid}/scenes/render", json={"mode": "preview"})
    assert job.status_code == 202, job.text
    finished = client.get(f"/api/v1/renders/{job.json()['id']}").json()  # background task already ran
    assert finished["status"] == "succeeded", finished["error"]
    assert len(blender.specs) == len(script["scenes"])
    assert all(s["engine"] == "cinematic" for s in blender.specs)

    final = client.post(f"/api/v1/projects/{pid}/assemble", json={"mode": "draft"})
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


PRODUCTION_V1 = REPO / "productions" / "archive" / "what_if_earth_stops_v1_planet" / "production.json"


def test_planet_centred_v1_production_is_rejected_by_the_human_impact_rule():
    from app.services.production.short import ProductionError, load_production

    data = json.loads(PRODUCTION_V1.read_text())
    for scene, spec in zip(data["script"]["scenes"], data["scenes"], strict=True):  # declare its real scales
        scene["scale"] = "global" if spec["environment"]["type"] == "space" else "street"
    path = REPO / "out" / "_v1_scaled.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False))
    with pytest.raises(ProductionError, match="human scale"):
        load_production(path)


def _second_production(tmp_path) -> Path:
    """A different script, to prove the producer is not tied to the first Short."""
    scene = storyboard_scene(0)
    script_scenes = [
        {
            "beat": "hook",
            "narration": "¿Y si midieras doce metros?",
            "visual": "x",
            "duration_seconds": 2,
            "claims": [],
        },
        {
            "beat": "setup",
            "narration": "Tu corazón tendría que bombear mucho más.",
            "visual": "x",
            "duration_seconds": 3,
            "claims": [{"text": "El volumen crece con el cubo", "type": "established", "source": ""}],
        },
        *[
            {
                "beat": "escalation",
                "narration": f"Consecuencia {i}.",
                "visual": "x",
                "duration_seconds": 2,
                "claims": [{"text": f"c{i}", "type": "estimate", "source": ""}],
            }
            for i in range(3)
        ],
        {"beat": "ending", "narration": "¿Te atreverías?", "visual": "x", "duration_seconds": 2, "claims": []},
    ]
    for item in script_scenes:
        if item["beat"] in ("escalation", "climax"):
            item.setdefault("human_subject", "tú")
            item.setdefault("consequence", "lo que cuenta la narración")
    production = {
        "id": "second",
        "format": "short",
        "seed": 9,
        "script": {
            "title_question": "¿Qué pasaría si midieras doce metros?",
            "hook": "¿Y si midieras doce metros?",
            "ending_type": "question",
            "ending_line": "¿Te atreverías?",
            "scenes": script_scenes,
            "visual_bible": {"look": "procedural", "recurring_subjects": []},
        },
        "scenes": [{**scene, "duration_seconds": 2.0, "sfx": [{"type": "whoosh", "at": 0.0}]} for _ in script_scenes],
    }
    path = tmp_path / "second.json"
    path.write_text(json.dumps(production, ensure_ascii=False))
    return path


@requires_ffmpeg
def test_produce_short_from_another_script(tmp_path):
    from app.services.production.short import produce_short

    blender = _StubBlender()
    report = produce_short(
        _second_production(tmp_path),
        "draft",
        tmp_path / "out",
        blender=blender,
        ffmpeg=ffmpeg,
        tts=_StubVoice(),
        log=lambda *_: None,
    )
    assert report["resolution"] == "540x960" and report["has_audio"]
    assert len(report["scenes"]) == 6 and len(blender.specs) == 6
    expected = report["timeline"][-1]["start"] + report["timeline"][-1]["duration"]
    assert abs(report["duration_seconds"] - expected) < 0.1
    # Preview: a fragment of chosen scenes only.
    preview = produce_short(
        _second_production(tmp_path),
        "preview",
        tmp_path / "out",
        blender=_StubBlender(),
        ffmpeg=ffmpeg,
        tts=_StubVoice(),
        scenes=[0, 1],
        log=lambda *_: None,
    )
    assert preview["resolution"] == "360x640" and len(preview["scenes"]) == 2
    # hd: scenes rendered at 720p (4 samples) and upscaled, so the upload is 1080x1920; a second run reuses clips.
    hd_blender = _StubBlender()
    kwargs = dict(ffmpeg=ffmpeg, tts=_StubVoice(), log=lambda *_: None)
    hd = produce_short(_second_production(tmp_path), "hd", tmp_path / "out", blender=hd_blender, **kwargs)
    assert hd["resolution"] == "1080x1920" and len(hd_blender.specs) == 6
    again = _StubBlender()
    produce_short(_second_production(tmp_path), "hd", tmp_path / "out", blender=again, **kwargs)
    assert again.specs == []


def test_production_rejects_broken_files(tmp_path):
    from app.services.production.short import ProductionError, load_production

    path = _second_production(tmp_path)
    data = json.loads(path.read_text())
    data["scenes"] = data["scenes"][:-1]
    path.write_text(json.dumps(data))
    with pytest.raises(ProductionError, match="one 3D scene per script scene"):
        load_production(path)
