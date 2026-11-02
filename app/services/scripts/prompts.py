"""Prompt templates for script generation. Bump PROMPT_VERSION on any change."""

from app.models.enums import VideoFormat

PROMPT_VERSION = "script-v1"

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "narration": {"type": "string"},
                    "visual": {"type": "string"},
                    "duration_seconds": {"type": "number"},
                },
                "required": ["narration", "visual", "duration_seconds"],
                "additionalProperties": False,
            },
        },
        "call_to_action": {"type": "string"},
    },
    "required": ["hook", "scenes", "call_to_action"],
    "additionalProperties": False,
}

_FORMAT_GUIDANCE = {
    VideoFormat.SHORT: (
        "This is a vertical YouTube Short (9:16). The first 2 seconds must stop the scroll. "
        "Use short, punchy sentences, one idea per scene, 3-8 scenes, and fast pacing. "
        "End with a loop-friendly line or a quick call to action."
    ),
    VideoFormat.LONG: (
        "This is a horizontal long-form YouTube video (16:9). Open with a hook that states "
        "the payoff, then structure the video into clear sections with smooth transitions. "
        "Keep viewers watching with open loops and pattern interrupts. "
        "Use as many scenes as the target length needs."
    ),
}

SYSTEM_PROMPT = (
    "You are an experienced YouTube scriptwriter. You write accurate, original scripts "
    "for faceless narrated videos. Do not invent statistics or quotes; if a fact is "
    "uncertain, phrase it as such. 'narration' is the exact voiceover text. 'visual' "
    "describes what should be on screen. 'duration_seconds' is the estimated speaking "
    "time of that scene at a natural pace (about 150 words per minute)."
)


def build_script_prompt(
    *,
    video_format: VideoFormat,
    topic: str,
    working_title: str,
    target_duration_seconds: int,
    language: str,
    niche: str | None,
    style_guide: str | None,
    notes: str | None,
) -> str:
    parts = [
        _FORMAT_GUIDANCE[video_format],
        f"Working title: {working_title}",
        f"Topic: {topic}",
        f"Target length: about {target_duration_seconds} seconds.",
        f"Language: write the script in '{language}'.",
    ]
    if niche:
        parts.append(f"Channel niche: {niche}")
    if style_guide:
        parts.append(f"Channel style guide:\n{style_guide}")
    if notes:
        parts.append(f"Producer notes:\n{notes}")
    return "\n\n".join(parts)
