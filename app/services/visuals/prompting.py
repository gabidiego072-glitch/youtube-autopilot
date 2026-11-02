"""Shot prompts with visual continuity.

Every scene prompt = the scene's shot + the descriptions of the recurring
subjects it mentions + the channel's hyper-realistic look + the script's look
and palette. One seed per project keeps generations consistent.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.content.profile import VISUAL_NEGATIVE, VISUAL_STYLE

# Generation sizes (multiples of 64, ~1 MP) per aspect ratio; upscaled/cropped at edit time.
SIZES = {"9:16": (768, 1344), "16:9": (1344, 768)}


@dataclass(frozen=True)
class ShotPrompt:
    scene_index: int
    prompt: str
    negative_prompt: str
    seed: int
    width: int
    height: int


def project_seed(project_id: str) -> int:
    return int(hashlib.sha256(project_id.encode()).hexdigest()[:8], 16)


def build_shot_prompts(
    scenes: list[dict], visual_bible: dict | None, *, aspect: str, project_id: str
) -> list[ShotPrompt]:
    bible = visual_bible or {}
    subjects = bible.get("recurring_subjects", [])
    width, height = SIZES[aspect]
    framing = "vertical 9:16 composition" if aspect == "9:16" else "wide 16:9 composition"
    seed = project_seed(project_id)
    shots = []
    for index, scene in enumerate(scenes):
        visual = scene["visual"]
        mentioned = [s for s in subjects if s["name"].lower() in visual.lower()]
        continuity = "; ".join(f"{s['name']}: {s['description']}" for s in mentioned)
        parts = [visual, continuity, bible.get("look", ""), bible.get("palette", ""), framing, VISUAL_STYLE]
        shots.append(
            ShotPrompt(
                scene_index=index,
                prompt=". ".join(p.strip().rstrip(".") for p in parts if p and p.strip()),
                negative_prompt=VISUAL_NEGATIVE,
                seed=seed,
                width=width,
                height=height,
            )
        )
    return shots
