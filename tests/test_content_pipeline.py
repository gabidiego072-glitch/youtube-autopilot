"""Ideas, research, script structure, fact-check, learning feedback (no external services)."""

import copy

import httpx
import pytest

from app.content.profile import is_off_topic
from app.core.errors import ProviderError
from app.models.enums import FactCheckStatus, VideoFormat
from app.services.analytics.metrics import DerivedMetrics
from app.services.factcheck.checker import decide
from app.services.ideas.generator import generate_ideas, is_duplicate, normalize, weighted_score
from app.services.learning.analyzer import VideoPerformance, analyze
from app.services.learning.feedback import category_weights, top_premises
from app.services.research.briefing import build_brief
from app.services.research.wikipedia import WikipediaClient
from app.services.scripts.generator import ScriptDraft, structure_problems
from tests.conftest import IDEAS_RESPONSE, SCRIPT_RESPONSE, StubAIProvider
from tests.helpers import create_project


def test_off_topic_filter():
    assert is_off_topic("¿Qué pasaría si vivieras dentro de un videojuego?")
    assert is_off_topic("Top gaming moments")
    assert not is_off_topic("¿Qué pasaría si la gravedad se duplicase?")


def test_duplicate_detection_ignores_accents_and_prefix():
    assert normalize("¿Qué pasaría si la Tierra dejase de girar?") == "la tierra dejase de girar"
    assert is_duplicate("Que pasaria si la tierra dejara de girar", ["¿Qué pasaría si la Tierra dejase de girar?"])
    assert not is_duplicate("¿Qué pasaría si la Luna desapareciera?", ["¿Qué pasaría si la Tierra dejase de girar?"])


def test_weighted_score_clamps_and_applies_category_weight():
    scores = {"curiosity": 10, "human_impact": 10, "visual_potential": 10, "scientific_grounding": 10, "evergreen": 10}
    assert weighted_score(scores) == 10.0
    assert weighted_score(scores, 1.2) == 12.0
    assert weighted_score({**scores, "curiosity": 99}) == 10.0


def test_generate_ideas_filters_and_ranks():
    ai = StubAIProvider([IDEAS_RESPONSE])
    ideas = generate_ideas(
        ai,
        count=5,
        language="es",
        existing_premises=["¿Qué pasaría si la Tierra dejase de girar?"],
        category_weights={"human_body": 1.25},
        top_premises=["¿Qué pasaría si vivieses 1.000 años?"],
    )
    premises = [i.premise for i in ideas]
    # Game premise, duplicate and non-question are dropped; ranking uses category weight.
    assert premises == ["¿Qué pasaría si dejaras de dormir?", "¿Qué pasaría si la Luna desapareciera?"]
    prompt = ai.calls[0]["prompt"]
    assert "human_body 1.25" in prompt and "vivieses 1.000 años" in prompt
    assert "Never propose anything about video games" in ai.calls[0]["system"]


def _perf(i, category, views, ending="question", comments=0):
    metrics = DerivedMetrics(
        views=views, impressions_ctr=None, engagement_rate=None, retention_ratio=None, subscribers_per_1k_views=None
    )
    return VideoPerformance(
        project_id=str(i),
        title=f"p{i}",
        format=VideoFormat.SHORT,
        metrics=metrics,
        category=category,
        ending_type=ending,
        comments=comments,
    )


def test_learning_feedback_weights_and_insights():
    videos = [_perf(i, "space_and_astronomy", 3000 + i, "question", 90) for i in range(3)]
    videos += [_perf(10 + i, "human_body", 500 + i, "surprising_conclusion", 5) for i in range(3)]
    weights = category_weights(videos)
    assert weights["space_and_astronomy"] == 1.25 and weights["human_body"] == 0.8
    assert top_premises(videos, 1) == ["p2"]
    kinds = {i.kind: i for i in analyze(videos)}
    assert "space_and_astronomy" in kinds["category_comparison"].title
    assert "question" in kinds["ending_comparison"].title
    assert category_weights(videos[:2]) == {}  # too little data -> neutral


def _draft(data=None):
    return ScriptDraft(**(data or SCRIPT_RESPONSE), provider="stub", model="m")


def test_script_structure_rules():
    assert structure_problems(_draft(), VideoFormat.SHORT) == []
    bad = copy.deepcopy(SCRIPT_RESPONSE)
    bad["hook"] = "una frase de gancho demasiado larga que nadie escucharía entera"
    bad["ending_line"] = "Sin pregunta"
    bad["scenes"] = bad["scenes"][1:]
    problems = " ".join(structure_problems(_draft(bad), VideoFormat.SHORT))
    assert "first scene" in problems and "Hook" in problems and "'?'" in problems
    assert "escalation" in " ".join(structure_problems(_draft(), VideoFormat.LONG))
    gaming = copy.deepcopy(SCRIPT_RESPONSE)
    gaming["scenes"][1]["narration"] = "Como en un videojuego."
    assert any("gaming" in p for p in structure_problems(_draft(gaming), VideoFormat.SHORT))


def test_fact_check_decision():
    types = {"a": "established", "b": "speculation"}
    assert decide([{"claim": "a", "verdict": "correct"}], types) == FactCheckStatus.PASSED
    assert decide([{"claim": "a", "verdict": "incorrect"}], types) == FactCheckStatus.NEEDS_REVISION
    assert decide([{"claim": "b", "verdict": "mislabeled"}], types) == FactCheckStatus.NEEDS_REVISION
    assert decide([{"claim": "a", "verdict": "unverifiable"}], types) == FactCheckStatus.NEEDS_REVISION
    assert decide([{"claim": "b", "verdict": "unverifiable"}], types) == FactCheckStatus.PASSED


def _wiki(handler) -> WikipediaClient:
    return WikipediaClient("es", "test-agent", client=httpx.Client(transport=httpx.MockTransport(handler)))


def _wiki_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["User-Agent"] == "test-agent"
    if request.url.path == "/w/api.php":
        return httpx.Response(200, json={"query": {"search": [{"title": "Rotación de la Tierra"}]}})
    return httpx.Response(
        200,
        json={
            "type": "standard",
            "title": "Rotación de la Tierra",
            "extract": "La Tierra gira una vez cada 23 h 56 min.",
            "content_urls": {"desktop": {"page": "https://es.wikipedia.org/wiki/Rotaci%C3%B3n_de_la_Tierra"}},
        },
    )


CONCEPTS = {"concepts": [{"concept": "rotación", "search_query": "Rotación de la Tierra", "why": "base"}]}
URL = "https://es.wikipedia.org/wiki/Rotaci%C3%B3n_de_la_Tierra"


def test_research_brief_with_sources():
    facts = {
        "facts": [
            {"fact": "Gira cada 23 h 56 min", "type": "established", "source_url": URL},
            {"fact": "Invented", "type": "established", "source_url": "https://evil.example"},
        ]
    }
    ai = StubAIProvider([CONCEPTS, facts])
    brief = build_brief(ai, _wiki(_wiki_handler), premise="¿Y si la Tierra se parase?", language="es")
    assert brief.status == "complete"
    assert brief.sources[0]["url"] == URL
    assert [f["fact"] for f in brief.key_facts] == ["Gira cada 23 h 56 min"]  # facts must cite a real source
    assert URL in ai.calls[1]["prompt"]


def test_research_brief_when_wikipedia_is_unavailable():
    brief = build_brief(
        StubAIProvider([CONCEPTS]),
        _wiki(lambda r: httpx.Response(429)),
        premise="¿Y si la Tierra se parase?",
        language="es",
    )
    assert brief.status == "no_sources" and brief.key_facts == [] and "429" in brief.errors[0]


def test_research_brief_requires_concepts():
    with pytest.raises(ProviderError):
        build_brief(StubAIProvider([{"concepts": []}]), None, premise="x", language="es")


def test_ideas_and_research_api(make_client, channel):
    from app.api.deps import provide_wikipedia

    ai = StubAIProvider([IDEAS_RESPONSE, CONCEPTS, {"facts": []}, SCRIPT_RESPONSE])
    client = make_client(ai=ai)
    client.app.dependency_overrides[provide_wikipedia] = lambda: _wiki(_wiki_handler)
    create_project(client, channel["id"], working_title="¿Qué pasaría si la Tierra dejase de girar?")

    ideas = client.post(f"/api/v1/channels/{channel['id']}/ideas/generate", json={"count": 5})
    assert ideas.status_code == 201, ideas.text
    assert [i["premise"] for i in ideas.json()] == [
        "¿Qué pasaría si la Luna desapareciera?",
        "¿Qué pasaría si dejaras de dormir?",
    ]
    best = ideas.json()[0]
    project = client.post(f"/api/v1/ideas/{best['id']}/select", json={"format": "short"})
    assert project.status_code == 201, project.text
    assert project.json()["category"] == "space_and_astronomy" and project.json()["idea_id"] == best["id"]
    assert client.post(f"/api/v1/ideas/{best['id']}/select", json={"format": "short"}).status_code == 409
    remaining = client.get(f"/api/v1/channels/{channel['id']}/ideas").json()
    assert [i["premise"] for i in remaining] == ["¿Qué pasaría si dejaras de dormir?"]
    assert client.post(f"/api/v1/ideas/{remaining[0]['id']}/reject").json()["status"] == "rejected"

    pid = project.json()["id"]
    brief = client.post(f"/api/v1/projects/{pid}/research")
    assert brief.status_code == 201 and brief.json()["status"] == "complete"
    client.post(f"/api/v1/projects/{pid}/scripts/generate")
    assert URL in ai.calls[-1]["prompt"]  # the script is grounded in the research sources


def test_human_impact_rule_rejects_planet_heavy_scripts():
    planet = copy.deepcopy(SCRIPT_RESPONSE)
    for scene in planet["scenes"][1:6]:
        scene["scale"] = "global"
    problems = " ".join(structure_problems(_draft(planet), VideoFormat.SHORT))
    assert "human scale" in problems and "global" in problems

    no_consequence = copy.deepcopy(SCRIPT_RESPONSE)
    no_consequence["scenes"][2]["consequence"] = ""
    assert any("consequence" in p for p in structure_problems(_draft(no_consequence), VideoFormat.SHORT))


def test_prompts_carry_the_human_impact_rule():
    from app.services.ideas.generator import SYSTEM_PROMPT as IDEAS
    from app.services.scenes.planner import SYSTEM_PROMPT as STORYBOARD
    from app.services.scripts.prompts import SYSTEM_PROMPT as SCRIPT

    for prompt in (IDEAS, SCRIPT, STORYBOARD):
        assert "Human-impact rule" in prompt
    assert "human_impact" in IDEAS and "'scale'" in SCRIPT
    # Keep a margin below the hard 70% / 15% validator limits so model timing drift does not reject a valid story.
    assert "at least 80% human-scale duration" in SCRIPT
    assert "10% or less of the total" in SCRIPT
    assert "Hard limits" in SCRIPT


def test_simple_premises_are_preferred_over_technical_ones():
    from app.services.ideas.generator import MAX_PREMISE_WORDS, SYSTEM_PROMPT, premise_words

    technical = "¿Qué pasaría si los árboles de las ciudades dejaran de absorber dióxido de carbono hoy?"
    simple = "¿Qué pasaría si no existieran los árboles desde mañana?"
    assert premise_words(simple) <= MAX_PREMISE_WORDS < premise_words(technical)
    assert "No technical terms" in SYSTEM_PROMPT
