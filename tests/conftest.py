import os
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 - registers all tables
from app.api.deps import provide_ai, provide_session_factory
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import build_engine, get_db
from app.main import create_app
from app.services.ai.base import GenerationResult


class StubAIProvider:
    """Test double: returns canned JSON and records each call. Never used outside tests."""

    name = "stub"
    model = "stub-model"

    def __init__(self, responses: list[dict] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict] = []

    def generate_json(self, *, system: str, prompt: str, schema: dict) -> GenerationResult:
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        return GenerationResult(data=self.responses.pop(0), provider=self.name, model=self.model)


def make_settings(**overrides) -> Settings:
    base = {
        "environment": "test",
        "database_url": "sqlite://",
        "anthropic_api_key": None,
        "planned_topics_enabled": False,
    }
    return Settings(_env_file=None, **{**base, **overrides})


@pytest.fixture
def settings() -> Settings:
    return make_settings()


# Set TEST_DATABASE_URL to run the whole suite against PostgreSQL (it is wiped per test).
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


@pytest.fixture
def db_session_factory() -> Iterator[sessionmaker[Session]]:
    engine = build_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(db_session_factory) -> Iterator[Session]:
    with db_session_factory() as session:
        yield session


@pytest.fixture
def make_client(db_session_factory) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def _make(settings: Settings | None = None, ai: StubAIProvider | None = None) -> TestClient:
        settings = settings or make_settings()
        application = create_app(settings)

        def _get_db():
            with db_session_factory() as session:
                yield session

        application.dependency_overrides[get_db] = _get_db
        application.dependency_overrides[get_settings] = lambda: settings
        application.dependency_overrides[provide_session_factory] = lambda: db_session_factory
        if ai is not None:
            application.dependency_overrides[provide_ai] = lambda: ai
        client = TestClient(application)
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.close()


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


@pytest.fixture
def channel(client) -> dict:
    response = client.post("/api/v1/channels", json={"name": "Qué Pasaría Si", "niche": "ciencia hipotética"})
    assert response.status_code == 201
    return response.json()


def _scene(
    beat: str,
    narration: str,
    visual: str,
    seconds: float,
    claims: list[tuple[str, str]],
    scale: str = "street",
    subject: str = "Lucía, una vecina",
    consequence: str = "",
) -> dict:
    return {
        "beat": beat,
        "narration": narration,
        "visual": visual,
        "duration_seconds": seconds,
        "scale": scale,
        "human_subject": subject,
        "consequence": consequence or ("the effect described in the narration" if claims else ""),
        "claims": [{"text": t, "type": k, "source": ""} for t, k in claims],
    }


SCRIPT_RESPONSE = {
    "title_question": "¿Qué pasaría si la Tierra dejase de girar?",
    "hook": "La Tierra frena en seco.",
    "scenes": [
        _scene("hook", "La Tierra frena en seco.", "The narrator, standing on a beach at dawn", 2, []),
        _scene(
            "setup",
            "Ahora mismo giramos a unos 1.670 km/h en el ecuador.",
            "Earth from orbit",
            4,
            [("El ecuador gira a unos 1.670 km/h", "established")],
        ),
        _scene(
            "escalation",
            "Todo lo que no esté anclado saldría disparado hacia el este.",
            "Wind tearing a city",
            4,
            [("Los objetos conservarían su velocidad", "established")],
        ),
        _scene(
            "escalation",
            "Los océanos se moverían hacia los polos.",
            "Ocean flooding a coastline",
            4,
            [("Los océanos migrarían hacia los polos", "estimate")],
        ),
        _scene(
            "escalation",
            "Un día duraría un año entero.",
            "The narrator under a frozen sun",
            3,
            [("Un día solar duraría un año", "established")],
        ),
        _scene(
            "climax",
            "Y el campo magnético podría debilitarse.",
            "Aurora fading over ice",
            3,
            [("El campo magnético podría debilitarse", "speculation")],
        ),
        _scene("ending", "¿Tú dónde vivirías?", "The narrator looking at the camera", 2, []),
    ],
    "ending_type": "question",
    "ending_line": "¿Tú dónde vivirías?",
    "visual_bible": {
        "look": "documentary, golden hour",
        "recurring_subjects": [{"name": "The narrator", "description": "woman in her 30s, red jacket"}],
        "palette": "warm oranges, deep blues",
        "camera_language": "handheld, wide lenses",
    },
}

# Human-impact rule: mostly street/interior/building scenes, one short global view.
for _scene_data, _scale in zip(
    SCRIPT_RESPONSE["scenes"], ["street", "global", "street", "building", "interior", "street", "street"], strict=True
):
    _scene_data["scale"] = _scale
SCRIPT_RESPONSE["scenes"][1]["duration_seconds"] = 3  # the global view stays under 15 % of the video

LONG_SCRIPT_RESPONSE = {
    **SCRIPT_RESPONSE,
    "scenes": SCRIPT_RESPONSE["scenes"][:2]
    + [
        _scene(
            "escalation",
            f"Consecuencia número {i}.",
            "The narrator in a storm",
            20,
            [(f"Consecuencia {i}", "estimate")],
        )
        for i in range(1, 7)
    ]
    + SCRIPT_RESPONSE["scenes"][-2:],
}

METADATA_RESPONSE = {
    "title": "¿Qué pasaría si la Tierra dejase de girar?",
    "description": "Un día duraría un año. #Shorts",
    "tags": ["rotación terrestre", "ciencia", "#Ciencia", "qué pasaría si"],
    "hashtags": ["Shorts", "#ciencia"],
    "thumbnail_text": "LA TIERRA SE PARA",
    "thumbnail_prompt": "Hyper-realistic photo of a city swept by wind",
    "pinned_comment": "¿Tú dónde vivirías?",
}

FACTCHECK_PASS = {
    "verdicts": [
        {"claim": c["text"], "verdict": "correct", "note": "", "correction": ""}
        for scene in SCRIPT_RESPONSE["scenes"]
        for c in scene["claims"]
    ],
    "summary": "OK",
}

IDEAS_RESPONSE = {
    "ideas": [
        {
            "premise": "¿Qué pasaría si la Luna desapareciera?",
            "category": "space_and_astronomy",
            "hook": "Esta noche, la Luna no sale.",
            "angle": "mareas, eje, noches",
            "science_basis": "mareas y estabilidad del eje",
            "curiosity": 9,
            "human_impact": 7,
            "visual_potential": 9,
            "scientific_grounding": 8,
            "evergreen": 10,
        },
        {
            "premise": "¿Qué pasaría si dejaras de dormir?",
            "category": "human_body",
            "hook": "Día 3 sin dormir.",
            "angle": "cerebro, cuerpo",
            "science_basis": "privación de sueño",
            "curiosity": 7,
            "human_impact": 7,
            "visual_potential": 6,
            "scientific_grounding": 9,
            "evergreen": 9,
        },
        {
            "premise": "¿Qué pasaría si vivieras dentro de un videojuego?",
            "category": "physics_laws",
            "hook": "Pulsa start.",
            "angle": "x",
            "science_basis": "x",
            "curiosity": 10,
            "human_impact": 7,
            "visual_potential": 10,
            "scientific_grounding": 1,
            "evergreen": 5,
        },
        {
            "premise": "¿Qué pasaría si la Tierra dejase de girar?",
            "category": "earth_and_climate",
            "hook": "Frenazo.",
            "angle": "x",
            "science_basis": "x",
            "curiosity": 9,
            "human_impact": 7,
            "visual_potential": 9,
            "scientific_grounding": 9,
            "evergreen": 9,
        },
        {
            "premise": "Sin interrogación al final",
            "category": "human_body",
            "hook": "x",
            "angle": "x",
            "science_basis": "x",
            "curiosity": 5,
            "human_impact": 7,
            "visual_potential": 5,
            "scientific_grounding": 5,
            "evergreen": 5,
        },
    ]
}


def storyboard_scene(index: int, scale: str = "street") -> dict:
    """A small valid planned scene whose environment can show the given scale."""
    if scale == "global":
        return {
            "environment": {"type": "space"},
            "characters": [],
            "props": [{"id": "earth", "type": "planet", "kind": "earth", "location": [0, 0, 0], "radius": 2.0}],
            "actions": [],
            "camera": {"shots": [{"time": 0.0, "location": [0.0, -9.0, 1.0], "target": "earth", "lens": 35}]},
        }
    environment = {"type": "interior"} if scale == "interior" else {"type": "city", "time_of_day": "day"}
    return {
        "environment": environment,
        "characters": [{"id": "narrator", "start": [-1.0, -0.5] if scale == "interior" else [-2.0, -5.5], "facing": 0}],
        "props": [],
        "actions": [
            {
                "type": "walk",
                "character": "narrator",
                "from": [-1.0, -0.5] if scale == "interior" else [-2.0, -5.5],
                "to": [0.5, -0.5] if scale == "interior" else [2.0, -5.5],
                "start": 0.0,
                "end": 1.0,
            }
        ],
        "camera": {
            "shots": [
                {
                    "time": 0.0,
                    "location": [0.0, -2.2, 1.5] if scale == "interior" else [-6.0, -6.0, 1.6],
                    "target": "narrator",
                    "lens": 24,
                },
                {
                    "time": 1.0,
                    "location": [0.2, -2.2, 1.5] if scale == "interior" else [-5.0, -6.0, 1.6],
                    "target": "narrator",
                    "lens": 26,
                },
            ]
        },
    }


STORYBOARD_RESPONSE = {
    "scenes": [storyboard_scene(i, scene["scale"]) for i, scene in enumerate(SCRIPT_RESPONSE["scenes"])]
}
