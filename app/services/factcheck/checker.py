"""Second-pass scientific review of a script's labelled claims.

This is an AI review against the research notes, not a substitute for a human
check of the sources; the API still requires human approval before publishing.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.content.profile import SCIENCE_RULES
from app.core.errors import ProviderError
from app.models.enums import FactCheckStatus
from app.services.ai.base import AIProvider

PROMPT_VERSION = "factcheck-v1"
VERDICTS = ("correct", "correct_but_imprecise", "mislabeled", "incorrect", "unverifiable")
BLOCKING = {"mislabeled", "incorrect"}

FACTCHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "verdict": {"type": "string", "enum": list(VERDICTS)},
                    "note": {"type": "string"},
                    "correction": {"type": "string"},
                },
                "required": ["claim", "verdict", "note", "correction"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["verdicts", "summary"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = f"""You are a strict science fact-checker for an educational YouTube channel about
hypothetical scenarios. The premise itself may be impossible; that is fine. Judge whether each claim about
what WOULD happen follows from real science, and whether its label is honest.
{SCIENCE_RULES}
Verdicts:
- correct: true (or a sound consequence of the premise) and correctly labelled.
- correct_but_imprecise: basically right but a number or wording should be tightened (give the correction).
- mislabeled: speculation or an estimate presented as established fact (or vice versa).
- incorrect: contradicts known science or the sources.
- unverifiable: cannot be checked with the notes or well-established knowledge.
Write notes and corrections in the script's language."""


class FactCheckResult(BaseModel):
    status: FactCheckStatus
    verdicts: list[dict]
    summary: str
    provider: str
    model: str

    def as_record(self) -> dict:
        return {
            "verdicts": self.verdicts,
            "summary": self.summary,
            "provider": self.provider,
            "model": self.model,
            "prompt_version": PROMPT_VERSION,
        }


def decide(verdicts: list[dict], claim_types: dict[str, str]) -> FactCheckStatus:
    for verdict in verdicts:
        if verdict["verdict"] in BLOCKING:
            return FactCheckStatus.NEEDS_REVISION
        # An unverifiable claim may stay only if the script already admits uncertainty.
        if verdict["verdict"] == "unverifiable" and claim_types.get(verdict["claim"]) == "established":
            return FactCheckStatus.NEEDS_REVISION
    return FactCheckStatus.PASSED


def fact_check(provider: AIProvider, *, premise: str, scenes: list[dict], research: dict | None) -> FactCheckResult:
    claims = [claim for scene in scenes for claim in scene.get("claims", [])]
    if not claims:
        raise ProviderError("The script has no labelled claims to check.")
    listing = "\n".join(f"{i}. [{c['type']}] {c['text']}" for i, c in enumerate(claims, start=1))
    notes = ""
    if research:
        notes = "\n".join(f"- {f['fact']} [{f['source_url']}]" for f in research.get("key_facts", []))
    prompt = (
        f"Premise: {premise}\n\nClaims (label in brackets):\n{listing}\n\n"
        f"Research notes:\n{notes or '(none available - use only well-established science)'}\n\n"
        "Return one verdict per claim, copying the claim text exactly."
    )
    result = provider.generate_json(system=SYSTEM_PROMPT, prompt=prompt, schema=FACTCHECK_SCHEMA)
    verdicts = [v for v in result.data.get("verdicts", []) if v.get("verdict") in VERDICTS]
    if len(verdicts) < len(claims):
        raise ProviderError("Fact-check did not return a verdict for every claim.")
    claim_types = {c["text"]: c["type"] for c in claims}
    return FactCheckResult(
        status=decide(verdicts, claim_types),
        verdicts=verdicts,
        summary=result.data.get("summary", ""),
        provider=result.provider,
        model=result.model,
    )
