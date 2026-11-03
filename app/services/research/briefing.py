"""Research brief: which real concepts a premise depends on, what trustworthy
sources say about them, and the key facts the script may use."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.content.profile import CHANNEL_CONCEPT, SCIENCE_RULES
from app.core.errors import ProviderError
from app.services.ai.base import AIProvider
from app.services.research.wikipedia import ResearchUnavailableError, WikipediaClient

logger = logging.getLogger(__name__)

CONCEPTS_SCHEMA = {
    "type": "object",
    "properties": {
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept": {"type": "string"},
                    "search_query": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["concept", "search_query", "why"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["concepts"],
    "additionalProperties": False,
}

FACTS_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string"},
                    "type": {"type": "string", "enum": ["established", "estimate"]},
                    "source_url": {"type": "string"},
                },
                "required": ["fact", "type", "source_url"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = f"""You are the science researcher of a YouTube channel.
{CHANNEL_CONCEPT}
{SCIENCE_RULES}"""


@dataclass
class Brief:
    concepts: list[dict]
    sources: list[dict]
    key_facts: list[dict]
    status: str  # complete | partial | no_sources
    provider: str
    model: str
    errors: list[str] = field(default_factory=list)


def build_brief(
    provider: AIProvider, wiki: WikipediaClient | None, *, premise: str, language: str, max_concepts: int = 6
) -> Brief:
    concepts_result = provider.generate_json(
        system=SYSTEM_PROMPT,
        prompt=(
            f"Premise: {premise}\n\nList the 3-{max_concepts} real scientific concepts this premise depends on "
            f"(for example: Earth's rotation, centrifugal force, square-cube law). 'search_query' must be a short "
            f"encyclopedia article title in '{language}'."
        ),
        schema=CONCEPTS_SCHEMA,
    )
    concepts = concepts_result.data.get("concepts", [])[:max_concepts]
    if not concepts:
        raise ProviderError("Research step returned no concepts.")

    sources, errors = [], []
    if wiki is not None:
        for concept in concepts:
            try:
                summary = wiki.lookup(concept["search_query"])
            except ResearchUnavailableError as exc:
                errors.append(str(exc))
                logger.warning("research lookup failed for %r: %s", concept["search_query"], exc)
                continue
            if summary and all(s["url"] != summary.url for s in sources):
                sources.append(
                    {
                        "title": summary.title,
                        "url": summary.url,
                        "extract": summary.extract[:1500],
                        "source": summary.source,
                    }
                )
    else:
        errors.append("No research source configured.")

    key_facts: list[dict] = []
    if sources:
        material = "\n\n".join(f"[{s['url']}] {s['title']}: {s['extract']}" for s in sources)
        facts_result = provider.generate_json(
            system=SYSTEM_PROMPT,
            prompt=(
                f"Premise: {premise}\n\nSources:\n{material}\n\nExtract the facts from these sources that a "
                f"script about the premise needs (numbers, mechanisms, limits). Use ONLY what the sources say; "
                f"set source_url to the URL in brackets. Write the facts in '{language}'."
            ),
            schema=FACTS_SCHEMA,
        )
        valid_urls = {s["url"] for s in sources}
        key_facts = [f for f in facts_result.data.get("facts", []) if f.get("source_url") in valid_urls]

    if not sources:
        status = "no_sources"
    elif len(sources) < len(concepts) or errors:
        status = "partial"
    else:
        status = "complete"
    return Brief(
        concepts=concepts,
        sources=sources,
        key_facts=key_facts,
        status=status,
        provider=concepts_result.provider,
        model=concepts_result.model,
        errors=errors,
    )
