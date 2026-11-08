"""Idea generation and selection for 'What would happen if...?' videos."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from pydantic import BaseModel, Field, ValidationError

from app.content.profile import (
    CHANNEL_CONCEPT,
    EXAMPLE_PREMISES,
    HUMAN_IMPACT_RULES,
    SCIENCE_RULES,
    category_list,
    is_off_topic,
)
from app.core.errors import ProviderError
from app.models.enums import ContentCategory
from app.services.ai.base import AIProvider

PROMPT_VERSION = "ideas-v3"
SCORE_WEIGHTS = {
    "curiosity": 0.30,
    "human_impact": 0.20,  # how strongly it changes daily life, homes and cities (human-impact rule)
    "visual_potential": 0.20,
    "scientific_grounding": 0.20,
    "evergreen": 0.10,
}
DUPLICATE_THRESHOLD = 0.82
MAX_PREMISE_WORDS = 10  # words after "¿Qué pasaría si"

IDEA_SCHEMA = {
    "type": "object",
    "properties": {
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "premise": {"type": "string"},
                    "category": {"type": "string", "enum": [c.value for c in ContentCategory]},
                    "hook": {"type": "string"},
                    "angle": {"type": "string"},
                    "science_basis": {"type": "string"},
                    "curiosity": {"type": "integer"},
                    "human_impact": {"type": "integer"},
                    "visual_potential": {"type": "integer"},
                    "scientific_grounding": {"type": "integer"},
                    "evergreen": {"type": "integer"},
                },
                "required": [
                    "premise",
                    "category",
                    "hook",
                    "angle",
                    "science_basis",
                    "curiosity",
                    "human_impact",
                    "visual_potential",
                    "scientific_grounding",
                    "evergreen",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ideas"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = f"""You are the head of content of a YouTube channel.
{CHANNEL_CONCEPT}

You propose premises for new videos. A strong premise:
- is a single, instantly understandable 'What would happen if...?' question,
- has consequences that escalate (small surprise -> big surprise -> mind-blowing end),
- can be answered with real science (physics, biology, astronomy, geology...),
- produces striking, filmable images,
- stays interesting for years (no news, no trends, no brands, no celebrities),
- is the title itself, so it is SHORT and SIMPLE: at most 10 words after "¿Qué pasaría si", everyday words a
  10-year-old understands, and a big, absolute change (no existieran, desaparecieran, se duplicara, para
  siempre, desde mañana). No technical terms in the premise (dióxido de carbono, conductividad, fotosíntesis,
  gravedad específica...): the science goes inside the video, never in the title.
  Bad: "¿Qué pasaría si los árboles de las ciudades dejaran de absorber dióxido de carbono hoy?"
  Good: "¿Qué pasaría si no existieran los árboles desde mañana?"
- passes the first-second test: the viewer instantly FEELS it in their own body or home (everyone falls
  asleep, the Earth brakes, friction vanishes). Abstract material or physics properties that need explaining
  before anything visible happens score low on curiosity and human_impact.
Never propose anything about video games or gaming.

{SCIENCE_RULES}

{HUMAN_IMPACT_RULES}

Score each idea honestly from 0 to 10 on: curiosity, human_impact (how clearly it changes people's lives, homes,
streets and cities - a premise that only affects the planet from afar scores low), visual_potential,
scientific_grounding (how much real science can explain it), evergreen.
'hook' is the first spoken line (at most 8 words). 'angle' says which
consequences the video will follow. 'science_basis' names the real science behind it."""


class IdeaDraft(BaseModel):
    premise: str = Field(min_length=10, max_length=300)
    category: ContentCategory
    hook: str = Field(min_length=3)
    angle: str = Field(min_length=3)
    science_basis: str = Field(min_length=3)
    scores: dict[str, int]
    score: float
    provider: str
    model: str


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\b(que pasaria si|what would happen if|y si|what if)\b", " ", text)
    return " ".join(text.split())


def premise_words(premise: str) -> int:
    """Words of the premise without the '¿Qué pasaría si' opener."""
    return len(normalize(premise).split())


def is_duplicate(premise: str, existing: list[str], threshold: float = DUPLICATE_THRESHOLD) -> bool:
    candidate = normalize(premise)
    return any(SequenceMatcher(None, candidate, normalize(other)).ratio() >= threshold for other in existing)


def weighted_score(scores: dict[str, int], category_weight: float = 1.0) -> float:
    base = sum(max(0, min(10, scores[name])) * weight for name, weight in SCORE_WEIGHTS.items())
    return round(base * category_weight, 2)


def build_prompt(
    *,
    count: int,
    language: str,
    avoid: list[str],
    category_weights: dict[str, float],
    top_premises: list[str],
    focus: str | None,
    trends: str | None = None,
) -> str:
    parts = [
        f"Propose {count} new premises. Write premise, hook, angle and science_basis in '{language}'.",
        "Format examples (do NOT repeat them):\n" + "\n".join(f"- {p}" for p in EXAMPLE_PREMISES),
        "Categories:\n" + category_list(),
    ]
    if focus:
        parts.append(f"Focus for this batch: {focus}")
    if trends:
        parts.append(trends)
    if top_premises:
        parts.append(
            "Our best performing videos so far (find new premises with similar appeal):\n"
            + "\n".join(f"- {p}" for p in top_premises)
        )
    if category_weights:
        ranked = sorted(category_weights.items(), key=lambda item: item[1], reverse=True)
        parts.append(
            "Category performance on this channel (1.0 = average): " + ", ".join(f"{c} {w:.2f}" for c, w in ranked)
        )
    if avoid:
        parts.append(
            "Already covered or proposed (avoid these and close variations):\n"
            + "\n".join(f"- {p}" for p in avoid[:200])
        )
    return "\n\n".join(parts)


def generate_ideas(
    provider: AIProvider,
    *,
    count: int,
    language: str,
    existing_premises: list[str],
    category_weights: dict[str, float] | None = None,
    top_premises: list[str] | None = None,
    focus: str | None = None,
    trends: str | None = None,
) -> list[IdeaDraft]:
    """Returns new, on-topic, non-duplicate ideas ranked by score (best first)."""
    weights = category_weights or {}
    prompt = build_prompt(
        count=count,
        language=language,
        avoid=existing_premises,
        category_weights=weights,
        top_premises=top_premises or [],
        focus=focus,
        trends=trends,
    )
    result = provider.generate_json(system=SYSTEM_PROMPT, prompt=prompt, schema=IDEA_SCHEMA)
    raw = result.data.get("ideas")
    if not isinstance(raw, list):
        raise ProviderError("Idea generation returned no 'ideas' list.")

    accepted: list[IdeaDraft] = []
    seen = list(existing_premises)
    for item in raw:
        try:
            scores = {name: int(item[name]) for name in SCORE_WEIGHTS}
            category = ContentCategory(item["category"])
            draft = IdeaDraft(
                premise=item["premise"].strip(),
                category=category,
                hook=item["hook"].strip(),
                angle=item["angle"].strip(),
                science_basis=item["science_basis"].strip(),
                scores=scores,
                score=weighted_score(scores, weights.get(category.value, 1.0)),
                provider=result.provider,
                model=result.model,
            )
        except (KeyError, ValueError, TypeError, ValidationError):
            continue
        text = " ".join((draft.premise, draft.hook, draft.angle))
        if is_off_topic(text) or not draft.premise.endswith("?") or is_duplicate(draft.premise, seen):
            continue
        if premise_words(draft.premise) > MAX_PREMISE_WORDS:  # long, technical titles get far fewer clicks
            draft.score = round(draft.score * 0.6, 2)
        seen.append(draft.premise)
        accepted.append(draft)
    return sorted(accepted, key=lambda d: d.score, reverse=True)
