"""Per-language wording the prompts need beyond "write in X": the title opener, good/bad title examples,
the POV counter and general tags. Spanish ("es") is the original channel; English ("en") is the second one.
"""

from __future__ import annotations

TITLE_GUIDE = {
    "es": (
        "Titles and premises start with '¿Qué pasaría si...?'. "
        "Bad: '¿Qué pasaría si los árboles dejaran de absorber dióxido de carbono?'. "
        "Good: '¿Qué pasaría si no existieran los árboles desde mañana?'."
    ),
    "en": (
        "Titles and premises start with 'What if...?' in natural American English (never translate from "
        "Spanish word by word). Bad: 'What would happen if trees stopped absorbing carbon dioxide?'. "
        "Good: 'What if trees disappeared tomorrow?'."
    ),
}

GENERAL_TAGS = {
    "es": "ciencia, curiosidades, qué pasaría si",
    "en": "science, what if, curiosity",
}

POV_VOICE = {
    "es": ('"Te despiertas...", "Coges el móvil...", "Bajas a la calle..."', '"DÍA 1 · 07:42"', "DÍA 1"),
    "en": ('"You wake up...", "You grab your phone...", "You walk down to the street..."', '"DAY 1 · 07:42"', "DAY 1"),
}

# Trend research: Wikipedia edition, YouTube region and search queries.
TRENDS = {
    "es": ("es", "ES", ("qué pasaría si", "qué pasaría si la tierra", "experimento mental ciencia")),
    "en": ("en", "US", ("what if", "what if the earth", "what would happen if science")),
}


def base(language: str) -> str:
    """'es-ES' -> 'es'; unknown languages fall back to Spanish wording."""
    code = (language or "es").split("-")[0].lower()
    return code if code in TITLE_GUIDE else "es"


def title_guide(language: str) -> str:
    return TITLE_GUIDE[base(language)]


EXAMPLE_PREMISES_EN = (
    "What if you grew one inch with every step?",
    "What if you could run at 600 mph?",
    "What if the Earth stopped spinning?",
    "What if gravity doubled tomorrow?",
)
