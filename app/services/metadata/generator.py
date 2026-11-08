"""Title, description, tags and thumbnail concept generation."""

from pydantic import BaseModel, ValidationError

from app.content.profile import CHANNEL_CONCEPT, is_off_topic
from app.core.errors import ProviderError
from app.models.enums import VideoFormat
from app.services.ai.base import AIProvider
from app.services.language import GENERAL_TAGS, base, title_guide
from app.services.metadata.rules import fit_tags, normalize_tags, validate_metadata

METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "thumbnail_text": {"type": "string"},
        "thumbnail_prompt": {"type": "string"},
        "pinned_comment": {"type": "string"},
    },
    "required": ["title", "description", "tags", "hashtags", "thumbnail_text", "thumbnail_prompt", "pinned_comment"],
    "additionalProperties": False,
}

SCIENCE_TECH_CATEGORY = "28"  # YouTube "Science & Technology"

SYSTEM_PROMPT = f"""You write YouTube metadata for this channel: {CHANNEL_CONCEPT}
Rules:
- Title: the 'What would happen if...?' question (in Spanish '¿Qué pasaría si...?'), at most 60 characters
  when possible, never over 100. Everyday words anyone understands in half a second, a big and simple change,
  no technical terms (keep the science for the description). Bad: '¿Qué pasaría si los árboles dejaran de
  absorber dióxido de carbono?'. Good: '¿Qué pasaría si no existieran los árboles?'. Curiosity without lying: the
  video must deliver what the title promises.
- Description: 2-3 hook sentences, then what the video explains, then a short line saying which parts are
  established science and which are estimates or speculation, then the sources (URLs) when given.
- Tags: specific science terms of the topic plus general ones (ciencia, curiosidades, qué pasaría si).
- Hashtags: 3-5; Shorts must include #Shorts.
- Never use '<' or '>'. Never mention video games or gaming.
- 'thumbnail_text': 2-5 bold words. 'thumbnail_prompt': which moment of the video (its 3D scene) makes the most
  striking thumbnail and why; the thumbnail is a frame of the rendered video, never a photo.
- 'pinned_comment': a question that invites viewers to answer in the comments."""


class MetadataDraft(BaseModel):
    title: str
    description: str
    tags: list[str]
    hashtags: list[str]
    thumbnail_text: str
    thumbnail_prompt: str
    pinned_comment: str
    category_id: str = SCIENCE_TECH_CATEGORY
    provider: str
    model: str


def generate_metadata(
    provider: AIProvider,
    *,
    video_format: VideoFormat,
    working_title: str,
    script_text: str,
    language: str,
    ending_line: str | None = None,
    sources: list[dict] | None = None,
) -> MetadataDraft:
    format_hint = (
        "This is a YouTube Short; keep the description brief and include #Shorts."
        if video_format == VideoFormat.SHORT
        else "This is a long-form video; the description may include a summary and chapters."
    )
    prompt = (
        f"{format_hint}\nLanguage: write every field in '{language}'. {title_guide(language)}\n"
        f"General tags in this language: {GENERAL_TAGS[base(language)]}.\n"
        f"Working title: {working_title}\n\nScript:\n{script_text}"
    )
    result = provider.generate_json(system=SYSTEM_PROMPT, prompt=prompt, schema=METADATA_SCHEMA)
    try:
        draft = MetadataDraft(**result.data, provider=result.provider, model=result.model)
    except ValidationError as exc:
        raise ProviderError("Generated metadata failed validation.") from exc

    draft.tags = fit_tags(normalize_tags(draft.tags))
    draft.hashtags = ["#" + tag for tag in normalize_tags(draft.hashtags)]
    problems = validate_metadata(draft.title, draft.description, draft.tags)
    if is_off_topic(" ".join((draft.title, draft.description, *draft.tags))):
        problems.append("Metadata mentions video games / gaming.")
    if problems:
        raise ProviderError("Generated metadata breaks YouTube rules: " + " ".join(problems))
    return draft
