"""The channel's editorial definition. Every generator (ideas, scripts, fact-checks,
visuals, metadata) builds its prompts from this module, so the whole pipeline
stays on one theme: curiosities, science, hypothetical situations and thought
experiments - mainly "What would happen if...?" videos.
"""

from app.models.enums import ContentCategory

CHANNEL_CONCEPT = (
    "A science-curiosity channel built on hypothetical situations and thought experiments, mainly "
    "'What would happen if...?' videos (in Spanish: '¿Qué pasaría si...?'). Each video takes one "
    "impossible or extreme premise and follows its consequences step by step using real science. "
    "The channel never covers video games, gaming, gameplay or game culture."
)

EXAMPLE_PREMISES = (
    "¿Qué pasaría si cada paso que das crecieras un centímetro?",
    "¿Qué pasaría si pudieras correr a 1.000 km/h?",
    "¿Qué pasaría si la Tierra dejase de girar?",
    "¿Qué pasaría si cada día te hicieras un 10% más pequeño?",
    "¿Qué pasaría si la gravedad se duplicase?",
    "¿Qué pasaría si vivieses 1.000 años?",
)

CATEGORY_DESCRIPTIONS = {
    ContentCategory.HUMAN_BODY: "the human body, physiology, senses, health",
    ContentCategory.SCALE_AND_SIZE: "growing, shrinking, extreme sizes and scaling laws",
    ContentCategory.SPEED_AND_MOTION: "extreme speeds, acceleration, movement",
    ContentCategory.EARTH_AND_CLIMATE: "planet Earth, rotation, oceans, atmosphere, climate",
    ContentCategory.SPACE_AND_ASTRONOMY: "the Sun, Moon, planets, stars, black holes",
    ContentCategory.PHYSICS_LAWS: "gravity, light, energy, fundamental constants",
    ContentCategory.TIME_AND_LIFESPAN: "time, ageing, living very long or very short lives",
    ContentCategory.NATURE_AND_ANIMALS: "animals, plants, ecosystems, evolution",
    ContentCategory.SOCIETY_AND_TECHNOLOGY: "civilisation, technology, energy and resources under the premise",
}

# Words that would pull a generator off-theme. Used to reject ideas.
OFF_TOPIC_TERMS = (
    "videojuego",
    "video game",
    "videogame",
    "gaming",
    "gamer",
    "gameplay",
    "minecraft",
    "fortnite",
    "roblox",
    "consola",
    "playstation",
    "xbox",
    "nintendo",
    "esports",
    "e-sports",
    "speedrun",
)

TONE_GUIDE = (
    "Dynamic, entertaining, easy to follow for a curious 14-year-old. Short sentences. Concrete images "
    "and comparisons instead of jargon (if a technical term is needed, explain it in the same sentence). "
    "Build tension: each consequence is bigger or stranger than the last."
)

SCIENCE_RULES = (
    "Scientific honesty rules: (1) Never invent numbers, studies or quotes. (2) Label every factual claim as "
    "'established' (textbook science), 'estimate' (calculated or extrapolated from real data; say it is "
    "approximate) or 'speculation' (plausible but unproven). (3) The narration itself must make the "
    "difference audible: use phrases like 'los científicos calculan', 'probablemente', 'nadie lo sabe con "
    "certeza'. (4) When the premise breaks physics, say which law it breaks, then follow the consequences "
    "consistently."
)

VISUAL_STYLE = (
    "Procedural 3D animation, generated entirely by code (Blender): clean stylised characters and worlds, "
    "soft physically based light and shadows, smooth cinematic camera moves. No photos, no AI-generated "
    "images, no hyper-realism, no text inside the scene (subtitles are added at the edit)."
)


# --- Human-impact rule (mandatory for every topic) ------------------------
# Videos show what would happen to US: people, homes, streets, cities and infrastructure.
# Planets, maps and global views are allowed only when they explain something, and never dominate.
HUMAN_SCALES = ("street", "interior", "building", "vehicle", "crowd")
OTHER_SCALES = ("aerial", "global")
SCENE_SCALES = HUMAN_SCALES + OTHER_SCALES
MIN_HUMAN_SHARE = 0.70  # of the video's duration
MAX_GLOBAL_SHARE = 0.15
MAX_GLOBAL_SCENES = 1

HUMAN_IMPACT_RULES = (
    "Human-impact rule (mandatory): the video shows what the phenomenon would do to the viewer, their home, "
    "their city and the people around them - not just what happens to the planet.\n"
    "1. Buildings: homes, skyscrapers, bridges, roads, hospitals, schools, factories suffering the consequences.\n"
    "2. People: real participants who react, act and are affected; never decoration.\n"
    "3. Streets and cities: recognisable urban places with cars, traffic lights, street lamps, benches, shops.\n"
    "4. Physical consequences: damage, movement, collapse, floods, fires, deformation - only what the science "
    "supports for this phenomenon.\n"
    "5. Human scale: street-level shots, building interiors, facades, vehicles, close perspectives; few aerial "
    "views, almost never space.\n"
    "6. Global information (the planet, maps): only when it is needed to explain something; at most one short "
    "scene; it never dominates the video.\n"
    "Scientific rigour comes first: never invent impossible consequences to get a spectacular scene. If people "
    "would have no time to react (an instantaneous catastrophe), do not show them sheltering. Depict harm to "
    "people in a stylised way, without blood or graphic injury."
)


def scale_problems(scales_and_durations: list[tuple[str, float]]) -> list[str]:
    """Checks the human-impact rule on (scale, duration) pairs. Empty list = OK."""
    total = sum(d for _, d in scales_and_durations) or 1.0
    unknown = sorted({s for s, _ in scales_and_durations if s not in SCENE_SCALES})
    problems = [f"Unknown scene scale(s): {unknown}."] if unknown else []
    human = sum(d for s, d in scales_and_durations if s in HUMAN_SCALES) / total
    global_scenes = [d for s, d in scales_and_durations if s == "global"]
    if human < MIN_HUMAN_SHARE:
        problems.append(f"Only {human:.0%} of the video is at human scale; at least {MIN_HUMAN_SHARE:.0%} required.")
    if len(global_scenes) > MAX_GLOBAL_SCENES:
        problems.append(f"{len(global_scenes)} global/planet scenes; at most {MAX_GLOBAL_SCENES} allowed.")
    if sum(global_scenes) / total > MAX_GLOBAL_SHARE:
        problems.append(f"Global views take {sum(global_scenes) / total:.0%}; at most {MAX_GLOBAL_SHARE:.0%}.")
    return problems


def is_off_topic(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in OFF_TOPIC_TERMS)


def category_list() -> str:
    return "\n".join(f"- {c.value}: {d}" for c, d in CATEGORY_DESCRIPTIONS.items())
