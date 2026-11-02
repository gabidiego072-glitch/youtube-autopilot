"""Visual prompts, AI image providers, Piper voice and the FFmpeg editor."""

import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from app.api.deps import provide_image_provider, provide_tts
from app.core.errors import IntegrationNotConfiguredError, ProviderError
from app.models.enums import VideoFormat
from app.services.editing.assembler import SceneMedia, assemble_video, subtitle_cues
from app.services.production.formats import FormatSpec
from app.services.rendering.ffmpeg import FFmpeg
from app.services.visuals.prompting import build_shot_prompts
from app.services.visuals.providers import ComfyUIClient, HuggingFaceImageProvider, get_image_provider
from app.services.voice.piper import PiperTTS
from tests.conftest import FACTCHECK_PASS, METADATA_RESPONSE, SCRIPT_RESPONSE, StubAIProvider, make_settings
from tests.helpers import create_project

ffmpeg = FFmpeg()
requires_ffmpeg = pytest.mark.skipif(not ffmpeg.is_available(), reason="ffmpeg not installed")
REPO = Path(__file__).resolve().parent.parent
VOICE = REPO / "models" / "voices" / "es_ES-davefx-medium.onnx"
PIPER = str(Path(sys.executable).parent / "piper")  # installed in the venv by piper-tts
TINY = FormatSpec(VideoFormat.SHORT, 180, 320, 24, 1, None, "1M", "96k")


def test_shot_prompts_keep_subjects_consistent():
    shots = build_shot_prompts(
        SCRIPT_RESPONSE["scenes"], SCRIPT_RESPONSE["visual_bible"], aspect="9:16", project_id="p1"
    )
    assert len(shots) == len(SCRIPT_RESPONSE["scenes"])
    assert (shots[0].width, shots[0].height) == (768, 1344)
    assert "red jacket" in shots[0].prompt  # recurring subject description injected
    assert "red jacket" not in shots[1].prompt  # not mentioned in that shot
    assert "photorealistic" in shots[1].prompt and "video game" in shots[1].negative_prompt
    assert len({s.seed for s in shots}) == 1


def test_image_provider_selection():
    with pytest.raises(IntegrationNotConfiguredError):
        get_image_provider(make_settings())
    assert get_image_provider(make_settings(hf_token="t")).name == "huggingface"
    assert get_image_provider(make_settings(comfyui_url="http://x", comfyui_image_workflow="w.json")).name == "comfyui"


def test_huggingface_provider(tmp_path):
    shot = build_shot_prompts(SCRIPT_RESPONSE["scenes"][:1], None, aspect="16:9", project_id="p")[0]

    def handler(request):
        assert request.headers["Authorization"] == "Bearer secret"
        body = json.loads(request.content)
        assert body["parameters"]["width"] == 1344
        return httpx.Response(200, content=b"\x89PNG fake", headers={"content-type": "image/png"})

    provider = HuggingFaceImageProvider(
        "secret",
        "black-forest-labs/FLUX.1-schnell",
        "https://hf.test/models",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    out = provider.generate(shot, tmp_path / "a.png")
    assert out.read_bytes().startswith(b"\x89PNG")

    failing = HuggingFaceImageProvider(
        "s",
        "m",
        "https://hf.test",
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(402, json={"error": "credits"}))),
    )
    with pytest.raises(ProviderError, match="402"):
        failing.generate(shot, tmp_path / "b.png")


def test_comfyui_workflow_placeholders(tmp_path):
    workflow = {"3": {"inputs": {"text": "{{prompt}}", "seed": "{{seed}}", "steps": 4}}}
    assert ComfyUIClient.fill(workflow, {"prompt": "a cat", "seed": 7}) == {
        "3": {"inputs": {"text": "a cat", "seed": 7, "steps": 4}}
    }

    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/prompt":
            assert json.loads(request.content)["prompt"]["3"]["inputs"]["text"] == "a cat"
            return httpx.Response(200, json={"prompt_id": "abc"})
        if request.url.path == "/history/abc":
            return httpx.Response(200, json={"abc": {"outputs": {"9": {"images": [{"filename": "o.png"}]}}}})
        return httpx.Response(200, content=b"img")

    wf = tmp_path / "wf.json"
    wf.write_text(json.dumps(workflow))
    client = ComfyUIClient("http://comfy", client=httpx.Client(transport=httpx.MockTransport(handler)))
    files = client.run(wf, {"prompt": "a cat", "seed": 1}, tmp_path / "out")
    assert files[0].read_bytes() == b"img" and calls == ["/prompt", "/history/abc", "/view"]


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


def _image(path: Path, color: str) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=400x300",
            "-frames:v",
            "1",
            str(path),
        ],
        check=True,
    )
    return path


def _tone(path: Path, seconds: float) -> Path:
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=f=300:d={seconds}", str(path)], check=True
    )
    return path


@requires_ffmpeg
def test_assemble_real_video(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=s=320x240:d=0.5", str(clip)], check=True
    )
    scenes = [
        SceneMedia(_image(tmp_path / "a.png", "navy"), _tone(tmp_path / "a.wav", 1.0), "¿Y si la Tierra se parase?"),
        SceneMedia(clip, _tone(tmp_path / "b.wav", 1.5), "Todo saldría volando.", is_video=True),
    ]
    music = _tone(tmp_path / "m.wav", 0.7)  # shorter than the video: it loops
    result = assemble_video(
        scenes, tmp_path / "out.mp4", spec=TINY, ffmpeg=ffmpeg, work_dir=tmp_path / "w", music_path=music
    )
    assert (result.width, result.height) == (180, 320) and result.has_audio
    assert 2.8 <= result.duration_seconds <= 3.3  # 1.0 + 1.5 + 2 x 0.25 pause
    assert "¿Y si la" in (tmp_path / "w" / "subtitles.srt").read_text()


class _StubImages:
    name = "stub-images"

    def generate(self, shot, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return _image(output_path, "teal")


class _StubVoice:
    name = "stub-voice"

    def synthesize(self, text, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return _tone(output_path, 0.4)


@requires_ffmpeg
def test_full_production_api(make_client, channel, tmp_path):
    """idea-less project -> script -> fact-check -> visuals -> voice -> edit -> metadata -> approve."""
    settings = make_settings(media_root=tmp_path / "media", edit_resolution_scale=0.12)
    client = make_client(settings, ai=StubAIProvider([SCRIPT_RESPONSE, FACTCHECK_PASS, METADATA_RESPONSE]))
    client.app.dependency_overrides[provide_image_provider] = lambda: _StubImages()
    client.app.dependency_overrides[provide_tts] = lambda: _StubVoice()
    pid = create_project(client, channel["id"])["id"]

    assert client.post(f"/api/v1/projects/{pid}/assemble", json={}).status_code == 409  # no script
    script = client.post(f"/api/v1/projects/{pid}/scripts/generate").json()
    assert client.post(f"/api/v1/projects/{pid}/assemble", json={}).status_code == 409  # no media yet
    client.post(f"/api/v1/projects/{pid}/scripts/{script['id']}/fact-check")

    images = client.post(f"/api/v1/projects/{pid}/visuals/generate", json={})
    assert images.status_code == 201, images.text
    assert {a["kind"] for a in images.json()} == {"image"} and len(images.json()) == len(script["scenes"])
    voice = client.post(f"/api/v1/projects/{pid}/voice/generate")
    assert voice.status_code == 201 and len(voice.json()) == len(script["scenes"])

    job = client.post(f"/api/v1/projects/{pid}/assemble", json={})
    assert job.status_code == 201, job.text
    assert job.json()["status"] == "succeeded" and Path(job.json()["output_path"]).is_file()
    assert client.get(f"/api/v1/projects/{pid}").json()["status"] == "rendered"

    client.post(f"/api/v1/projects/{pid}/metadata/generate")
    approved = client.post(f"/api/v1/projects/{pid}/approve")
    assert approved.status_code == 200, approved.text
    kinds = [a["kind"] for a in client.get(f"/api/v1/projects/{pid}/assets").json()]
    assert kinds.count("render_output") == 1


def test_visuals_without_provider_is_503(make_client, channel):
    client = make_client(ai=StubAIProvider([SCRIPT_RESPONSE]))
    pid = create_project(client, channel["id"])["id"]
    client.post(f"/api/v1/projects/{pid}/scripts/generate")
    response = client.post(f"/api/v1/projects/{pid}/visuals/generate", json={})
    assert response.status_code == 503 and "COMFYUI_URL" in response.json()["detail"]
