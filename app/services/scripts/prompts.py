"""Prompt templates for 'What would happen if...?' scripts. Bump PROMPT_VERSION on any change."""

from app.content.profile import (
    CHANNEL_CONCEPT,
    HUMAN_IMPACT_RULES,
    MAX_GLOBAL_SCENES,
    MIN_HUMAN_SHARE,
    SCENE_SCALES,
    SCIENCE_RULES,
    TONE_GUIDE,
    VISUAL_STYLE,
)
from app.models.enums import ClaimType, VideoFormat
from render_engines.core.catalog import catalog_text

PROMPT_VERSION = "whatif-script-v4"
HOOK_MAX_WORDS = 8  # ~2 seconds of fast narration
BEATS = ("hook", "setup", "escalation", "climax", "ending")

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title_question": {"type": "string"},
        "hook": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "beat": {"type": "string", "enum": list(BEATS)},
                    "narration": {"type": "string"},
                    "visual": {"type": "string"},
                    "duration_seconds": {"type": "number"},
                    "scale": {"type": "string", "enum": list(SCENE_SCALES)},
                    "human_subject": {"type": "string"},
                    "consequence": {"type": "string"},
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "type": {"type": "string", "enum": [c.value for c in ClaimType]},
                                "source": {"type": "string"},
                            },
                            "required": ["text", "type", "source"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "beat",
                    "narration",
                    "visual",
                    "duration_seconds",
                    "scale",
                    "human_subject",
                    "consequence",
                    "claims",
                ],
                "additionalProperties": False,
            },
        },
        "ending_type": {"type": "string", "enum": ["question", "surprising_conclusion"]},
        "ending_line": {"type": "string"},
        "visual_bible": {
            "type": "object",
            "properties": {
                "look": {"type": "string"},
                "recurring_subjects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}, "description": {"type": "string"}},
                        "required": ["name", "description"],
                        "additionalProperties": False,
                    },
                },
                "palette": {"type": "string"},
                "camera_language": {"type": "string"},
            },
            "required": ["look", "recurring_subjects", "palette", "camera_language"],
            "additionalProperties": False,
        },
    },
    "required": ["title_question", "hook", "scenes", "ending_type", "ending_line", "visual_bible"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = f"""You are the head writer of a YouTube channel.
{CHANNEL_CONCEPT}

Structure every script like this:
1. hook (first scene, at most {HOOK_MAX_WORDS} words, under 2 seconds): the most shocking consequence or
   the premise itself, said in a way that makes scrolling away impossible. No greetings, no "in this video".
2. setup: in one or two sentences, what the premise means in concrete terms.
3. escalation: consequences in order - first seconds, minutes, days, years (or small -> huge). Each scene
   must be bigger or stranger than the previous one.
4. climax: the most extreme consequence.
5. ending (last scene): a surprising conclusion OR a question the viewer will want to answer in the comments.
   'ending_line' repeats that final sentence exactly.

{TONE_GUIDE}

{HUMAN_IMPACT_RULES}
For every scene set 'scale' (street, interior, building, vehicle, crowd = human scale; aerial; global = the
planet, a map or space), 'human_subject' (who or what of ours is affected: a person, a family, a street, a
hospital...) and 'consequence' (the physical effect shown, which must be backed by one of the scene's claims).
At least {MIN_HUMAN_SHARE:.0%} of the duration must be at human scale and at most {MAX_GLOBAL_SCENES} scene may
be global.

{SCIENCE_RULES}
Put every factual statement of a scene in its 'claims' list with its type; 'source' is the source URL from the
research notes when one supports it, otherwise an empty string.

Visuals: {VISUAL_STYLE}
'visual' describes what the 3D scene shows (who/what, what they do, where the camera is), using only things the
3D engine can draw:
{catalog_text()}
Keep the same characters and places across scenes: define them once in 'visual_bible.recurring_subjects'
(name + look) and reuse the names: follow the same person, street or home through the video.

'duration_seconds' is the speaking time of the scene's narration at a lively pace (about 150 words/minute)."""

_FORMAT_GUIDANCE = {
    VideoFormat.SHORT: (
        "Format: vertical YouTube Short (9:16), 30-60 seconds. 6-10 fast scenes of 1-2 sentences. "
        "At least 3 escalation scenes. Vertical framing: keep the subject centred and tall in frame."
    ),
    VideoFormat.LONG: (
        "Format: horizontal long-form video (16:9). Cover the premise in depth: timeline of consequences, "
        "the science behind each step, and what scientists really know vs. estimate. Use as many scenes as "
        "the target length needs, with at least 6 escalation scenes. Add open loops ('but the worst part "
        "comes later') to keep viewers watching."
    ),
}


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
    research: dict | None = None,
) -> str:
    parts = [
        _FORMAT_GUIDANCE[video_format],
        f"Premise / working title: {working_title}",
        f"Topic details: {topic}",
        f"Target length: about {target_duration_seconds} seconds.",
        f"Language: write title_question, narration and ending_line in '{language}'. Visual descriptions in English.",
    ]
    if niche:
        parts.append(f"Channel niche: {niche}")
    if style_guide:
        parts.append(f"Channel style guide:\n{style_guide}")
    if notes:
        parts.append(f"Producer notes:\n{notes}")
    if research and (research.get("key_facts") or research.get("sources")):
        facts = "\n".join(f"- ({f['type']}) {f['fact']} [{f['source_url']}]" for f in research.get("key_facts", []))
        sources = "\n".join(f"- {s['title']}: {s['url']}" for s in research.get("sources", []))
        parts.append(
            "Research notes (prefer these facts; anything not covered here must be labelled honestly):\n"
            f"{facts or '(no extracted facts)'}\nSources:\n{sources}"
        )
    else:
        parts.append(
            "No research notes are available: rely only on well-established science and label every "
            "number that is not textbook knowledge as 'estimate' or 'speculation'."
        )
    return "\n\n".join(parts)
