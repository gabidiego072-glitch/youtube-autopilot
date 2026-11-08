"""Script generation for 'What would happen if...?' Shorts and long-form videos."""

from pydantic import BaseModel, Field, ValidationError

from app.content.profile import is_off_topic, scale_problems
from app.core.errors import ProviderError
from app.models.enums import ClaimType, VideoFormat
from app.services.ai.base import AIProvider
from app.services.production.formats import FormatSpec
from app.services.scripts.prompts import (
    BEATS,
    HOOK_MAX_WORDS,
    PROMPT_VERSION,
    SCRIPT_SCHEMA,
    SYSTEM_PROMPT,
    build_script_prompt,
)

WORDS_PER_SECOND = 2.5  # ~150 words per minute narration
MIN_ESCALATIONS = {VideoFormat.SHORT: 3, VideoFormat.LONG: 6}


class ClaimDraft(BaseModel):
    text: str = Field(min_length=1)
    type: ClaimType
    source: str = ""


class SceneDraft(BaseModel):
    beat: str
    narration: str = Field(min_length=1)
    visual: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0)
    scale: str = "street"
    human_subject: str = ""
    consequence: str = ""
    claims: list[ClaimDraft] = Field(default_factory=list)
    hud: str = ""  # on-screen counter for POV videos ("DÍA 1 · 07:42")


class VisualBible(BaseModel):
    look: str
    recurring_subjects: list[dict] = Field(default_factory=list)
    palette: str = ""
    camera_language: str = ""


class ScriptDraft(BaseModel):
    title_question: str = Field(min_length=5)
    hook: str = Field(min_length=1)
    scenes: list[SceneDraft] = Field(min_length=1)
    ending_type: str
    ending_line: str = Field(min_length=1)
    visual_bible: VisualBible
    provider: str
    model: str
    prompt_version: str = PROMPT_VERSION

    @property
    def call_to_action(self) -> str:
        return self.ending_line

    @property
    def full_text(self) -> str:
        return "\n\n".join(scene.narration.strip() for scene in self.scenes)

    @property
    def estimated_duration_seconds(self) -> float:
        """The larger of the model's scene estimates and a word-count estimate."""
        by_scenes = sum(scene.duration_seconds for scene in self.scenes)
        by_words = len(self.full_text.split()) / WORDS_PER_SECOND
        return round(max(by_scenes, by_words), 1)

    @property
    def claims(self) -> list[ClaimDraft]:
        return [claim for scene in self.scenes for claim in scene.claims]


def estimate_speech_seconds(text: str) -> float:
    return round(len(text.split()) / WORDS_PER_SECOND, 1)


QUESTION_WORDS = (  # English question endings (Spanish ones carry '¿')
    "and ",
    "so ",
    "what ",
    "would ",
    "could ",
    "how ",
    "why ",
    "which ",
    "who ",
    "where ",
    "do ",
    "did ",
    "will ",
    "can ",
)


def repair_ending(draft: ScriptDraft) -> None:
    """A question ending that only lacks its '?' is fixed instead of rejected."""
    line = draft.ending_line.rstrip()
    if draft.ending_type == "question" and not line.endswith("?"):
        if "¿" in line or line.lower().startswith(QUESTION_WORDS):
            fixed = line.rstrip(".!") + "?"
            last = draft.scenes[-1]
            if last.narration.rstrip().endswith(line):
                last.narration = last.narration.rstrip()[: -len(line)] + fixed
            draft.ending_line = fixed
        else:
            draft.ending_type = "surprising_conclusion"


def structure_problems(draft: ScriptDraft, video_format: VideoFormat) -> list[str]:
    """Checks the 'What would happen if' structure. Empty list = OK."""
    problems = []
    beats = [scene.beat for scene in draft.scenes]
    if any(beat not in BEATS for beat in beats):
        problems.append("Unknown scene beat.")
    if beats[0] != "hook":
        problems.append("The first scene must be the hook.")
    if beats[-1] != "ending":
        problems.append("The last scene must be the ending.")
    if beats.count("escalation") < MIN_ESCALATIONS[video_format]:
        problems.append(f"Needs at least {MIN_ESCALATIONS[video_format]} escalation scenes.")
    if len(draft.hook.split()) > HOOK_MAX_WORDS:
        problems.append(f"Hook is longer than {HOOK_MAX_WORDS} words.")
    if draft.ending_type not in ("question", "surprising_conclusion"):
        problems.append("Unknown ending type.")
    if draft.ending_type == "question" and not draft.ending_line.rstrip().endswith("?"):
        problems.append("A question ending must end with '?'.")
    if not draft.claims:
        problems.append("The script makes no labelled claims.")
    if is_off_topic(draft.full_text + " " + draft.title_question):
        problems.append("Script drifts into video game / gaming content.")
    # Human-impact rule: what happens to us, not just to the planet.
    problems += scale_problems([(scene.scale, scene.duration_seconds) for scene in draft.scenes])
    for index, scene in enumerate(draft.scenes):
        if scene.beat in ("escalation", "climax"):
            if not scene.consequence.strip() or not scene.human_subject.strip():
                problems.append(f"Scene {index} needs a human subject and the consequence it shows.")
            if not scene.claims:
                problems.append(f"Scene {index} shows a consequence with no scientific claim behind it.")
    return problems


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
    research: dict | None = None,
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
        research=research,
    )
    problems: list[str] = []
    for _attempt in range(2):  # one retry, telling the AI exactly what was wrong
        ask = prompt
        if problems:
            ask += (
                "\n\nYour previous script was rejected for these reasons; fix them and keep the same premise:\n- "
                + "\n- ".join(problems)
            )
        result = provider.generate_json(system=SYSTEM_PROMPT, prompt=ask, schema=SCRIPT_SCHEMA)
        try:
            draft = ScriptDraft(**result.data, provider=result.provider, model=result.model)
        except ValidationError as exc:
            problems = [f"The JSON failed validation ({exc.error_count()} error(s)); follow the schema exactly."]
            continue
        repair_ending(draft)
        problems = structure_problems(draft, spec.format)
        if not problems:
            break
    if problems:
        raise ProviderError("Generated script rejected: " + " ".join(problems))
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
