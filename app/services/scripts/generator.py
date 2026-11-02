"""Script generation for Shorts and long-form videos."""

from pydantic import BaseModel, Field, ValidationError

from app.core.errors import ProviderError
from app.models.enums import VideoFormat
from app.services.ai.base import AIProvider
from app.services.production.formats import FormatSpec
from app.services.scripts.prompts import (
    PROMPT_VERSION,
    SCRIPT_SCHEMA,
    SYSTEM_PROMPT,
    build_script_prompt,
)

WORDS_PER_SECOND = 2.5  # ~150 words per minute narration


class SceneDraft(BaseModel):
    narration: str = Field(min_length=1)
    visual: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0)


class ScriptDraft(BaseModel):
    hook: str = Field(min_length=1)
    scenes: list[SceneDraft] = Field(min_length=1)
    call_to_action: str = ""
    provider: str
    model: str
    prompt_version: str = PROMPT_VERSION

    @property
    def full_text(self) -> str:
        lines = [scene.narration.strip() for scene in self.scenes]
        if self.call_to_action.strip():
            lines.append(self.call_to_action.strip())
        return "\n\n".join(lines)

    @property
    def estimated_duration_seconds(self) -> float:
        """The larger of the model's scene estimates and a word-count estimate."""
        by_scenes = sum(scene.duration_seconds for scene in self.scenes)
        by_words = len(self.full_text.split()) / WORDS_PER_SECOND
        return round(max(by_scenes, by_words), 1)


def estimate_speech_seconds(text: str) -> float:
    return round(len(text.split()) / WORDS_PER_SECOND, 1)


def generate_script(
    provider: AIProvider,
    *,
    spec: FormatSpec,
    topic: str,
    working_title: str,
    target_duration_seconds: int,
    language: str,
    niche: str | None = None,
    style_guide: str | None = None,
    notes: str | None = None,
) -> ScriptDraft:
    prompt = build_script_prompt(
        video_format=spec.format,
        topic=topic,
        working_title=working_title,
        target_duration_seconds=target_duration_seconds,
        language=language,
        niche=niche,
        style_guide=style_guide,
        notes=notes,
    )
    result = provider.generate_json(system=SYSTEM_PROMPT, prompt=prompt, schema=SCRIPT_SCHEMA)
    try:
        draft = ScriptDraft(**result.data, provider=result.provider, model=result.model)
    except ValidationError as exc:
        raise ProviderError(f"Generated script failed validation: {exc.error_count()} error(s).") from exc

    if (
        spec.format == VideoFormat.SHORT
        and spec.max_duration_seconds is not None
        and draft.estimated_duration_seconds > spec.max_duration_seconds
    ):
        raise ProviderError(
            f"Generated Short runs ~{draft.estimated_duration_seconds}s, over the "
            f"{spec.max_duration_seconds}s limit. Regenerate or lower the target length."
        )
    return draft
