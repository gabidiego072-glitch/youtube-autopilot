"""Title, description, tags and thumbnail concept generation."""

from pydantic import BaseModel, ValidationError

from app.core.errors import ProviderError
from app.models.enums import VideoFormat
from app.services.ai.base import AIProvider
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
    },
    "required": ["title", "description", "tags", "hashtags", "thumbnail_text", "thumbnail_prompt"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You write YouTube metadata that earns clicks honestly: no clickbait the video "
    "does not deliver on. Title at most 70 characters when possible and never over 100. "
    "Never use '<' or '>'. 'thumbnail_text' is 2-5 bold words for the thumbnail. "
    "'thumbnail_prompt' describes the thumbnail image for an image model."
)


class MetadataDraft(BaseModel):
    title: str
    description: str
    tags: list[str]
    hashtags: list[str]
    thumbnail_text: str
    thumbnail_prompt: str
    provider: str
    model: str


def generate_metadata(
    provider: AIProvider,
    *,
    video_format: VideoFormat,
    working_title: str,
    script_text: str,
    language: str,
) -> MetadataDraft:
    format_hint = (
        "This is a YouTube Short; keep the description brief and include #Shorts."
        if video_format == VideoFormat.SHORT
        else "This is a long-form video; the description may include a summary and chapters."
    )
    prompt = f"{format_hint}\nLanguage: {language}\nWorking title: {working_title}\n\nScript:\n{script_text}"
    result = provider.generate_json(system=SYSTEM_PROMPT, prompt=prompt, schema=METADATA_SCHEMA)
    try:
        draft = MetadataDraft(**result.data, provider=result.provider, model=result.model)
    except ValidationError as exc:
        raise ProviderError("Generated metadata failed validation.") from exc

    draft.tags = fit_tags(normalize_tags(draft.tags))
    draft.hashtags = ["#" + tag for tag in normalize_tags(draft.hashtags)]
    problems = validate_metadata(draft.title, draft.description, draft.tags)
    if problems:
        raise ProviderError("Generated metadata breaks YouTube rules: " + " ".join(problems))
    return draft
