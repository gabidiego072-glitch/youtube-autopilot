"""AI image / video providers. All are optional and free to use when self-hosted
or within free tiers; none is called unless configured."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import Settings
from app.core.errors import IntegrationNotConfiguredError, ProviderError
from app.services.visuals.prompting import ShotPrompt


class ImageProvider(Protocol):
    name: str

    def generate(self, shot: ShotPrompt, output_path: Path) -> Path: ...


class HuggingFaceImageProvider:
    """Text-to-image via Hugging Face Inference Providers (free monthly credits with an HF token)."""

    name = "huggingface"

    def __init__(
        self, token: str, model: str, base_url: str, client: httpx.Client | None = None, timeout: float = 300.0
    ) -> None:
        self.model = model
        self._url = f"{base_url.rstrip('/')}/{model}"
        self._client = client or httpx.Client(timeout=timeout)
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "image/png"}

    def generate(self, shot: ShotPrompt, output_path: Path) -> Path:
        payload = {
            "inputs": shot.prompt,
            "parameters": {
                "width": shot.width,
                "height": shot.height,
                "seed": shot.seed,
                "negative_prompt": shot.negative_prompt,
            },
        }
        try:
            response = self._client.post(self._url, json=payload, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Hugging Face request failed: {exc}") from exc
        if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
            raise ProviderError(
                f"Hugging Face image generation failed (HTTP {response.status_code}): {response.text[:300]}"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        return output_path


class ComfyUIClient:
    """Runs an API-format ComfyUI workflow. String values like "{{prompt}}" are replaced
    before queueing, so any open model graph (FLUX, SDXL, Wan, LTX-Video...) can be used."""

    def __init__(
        self, base_url: str, client: httpx.Client | None = None, timeout: float = 600.0, poll_seconds: float = 2.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=60.0)
        self.timeout = timeout
        self.poll_seconds = poll_seconds

    @staticmethod
    def fill(workflow: dict, values: dict) -> dict:
        def replace(node):
            if isinstance(node, dict):
                return {k: replace(v) for k, v in node.items()}
            if isinstance(node, list):
                return [replace(v) for v in node]
            if isinstance(node, str) and node.startswith("{{") and node.endswith("}}"):
                return values.get(node[2:-2], node)
            return node

        return replace(workflow)

    def upload_image(self, path: Path) -> str:
        with path.open("rb") as fh:
            response = self._client.post(f"{self.base_url}/upload/image", files={"image": (path.name, fh)})
        response.raise_for_status()
        return response.json()["name"]

    def run(self, workflow_path: Path, values: dict, output_dir: Path) -> list[Path]:
        workflow = self.fill(json.loads(workflow_path.read_text(encoding="utf-8")), values)
        try:
            queued = self._client.post(
                f"{self.base_url}/prompt", json={"prompt": workflow, "client_id": str(uuid.uuid4())}
            )
            queued.raise_for_status()
            prompt_id = queued.json()["prompt_id"]
            deadline = time.monotonic() + self.timeout
            while True:
                history = self._client.get(f"{self.base_url}/history/{prompt_id}").json()
                if prompt_id in history and history[prompt_id].get("outputs"):
                    break
                if time.monotonic() > deadline:
                    raise ProviderError("ComfyUI job timed out.")
                time.sleep(self.poll_seconds)
            files = []
            for output in history[prompt_id]["outputs"].values():
                for item in output.get("images", []) + output.get("gifs", []) + output.get("videos", []):
                    data = self._client.get(
                        f"{self.base_url}/view",
                        params={
                            "filename": item["filename"],
                            "subfolder": item.get("subfolder", ""),
                            "type": item.get("type", "output"),
                        },
                    )
                    data.raise_for_status()
                    target = output_dir / item["filename"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data.content)
                    files.append(target)
        except httpx.HTTPError as exc:
            raise ProviderError(f"ComfyUI request failed: {exc}") from exc
        if not files:
            raise ProviderError("ComfyUI workflow produced no output files.")
        return files


class ComfyUIImageProvider:
    name = "comfyui"

    def __init__(self, client: ComfyUIClient, workflow: Path) -> None:
        self._client = client
        self._workflow = workflow

    def generate(self, shot: ShotPrompt, output_path: Path) -> Path:
        values = {
            "prompt": shot.prompt,
            "negative_prompt": shot.negative_prompt,
            "seed": shot.seed,
            "width": shot.width,
            "height": shot.height,
        }
        produced = self._client.run(self._workflow, values, output_path.parent / "_comfyui")
        output_path.write_bytes(produced[0].read_bytes())
        return output_path


class ComfyUIVideoProvider:
    """Image-to-video (e.g. Wan 2.x or LTX-Video workflows) for real camera/subject motion."""

    name = "comfyui-video"

    def __init__(self, client: ComfyUIClient, workflow: Path) -> None:
        self._client = client
        self._workflow = workflow

    def animate(self, image_path: Path, prompt: str, seconds: float, output_path: Path, seed: int = 0) -> Path:
        uploaded = self._client.upload_image(image_path)
        values = {"image": uploaded, "prompt": prompt, "seconds": seconds, "seed": seed}
        produced = self._client.run(self._workflow, values, output_path.parent / "_comfyui")
        output_path.write_bytes(produced[0].read_bytes())
        return output_path


def get_image_provider(settings: Settings) -> ImageProvider:
    if settings.image_provider_name == "comfyui":
        return ComfyUIImageProvider(
            ComfyUIClient(settings.comfyui_url, timeout=settings.visuals_timeout_seconds),
            settings.comfyui_image_workflow,
        )
    if settings.image_provider_name == "huggingface":
        return HuggingFaceImageProvider(
            settings.hf_token.get_secret_value(),
            settings.hf_image_model,
            settings.hf_inference_url,
            timeout=settings.visuals_timeout_seconds,
        )
    raise IntegrationNotConfiguredError(
        "No AI image provider configured. Set COMFYUI_URL + COMFYUI_IMAGE_WORKFLOW (self-hosted, free) or HF_TOKEN."
    )


def get_video_provider(settings: Settings) -> ComfyUIVideoProvider | None:
    """None means: animate stills with the free FFmpeg camera-motion fallback."""
    if settings.comfyui_url and settings.comfyui_video_workflow:
        return ComfyUIVideoProvider(
            ComfyUIClient(settings.comfyui_url, timeout=settings.visuals_timeout_seconds),
            settings.comfyui_video_workflow,
        )
    return None
