import os
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 - registers all tables
from app.api.deps import provide_ai
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
    base = {"environment": "test", "database_url": "sqlite://", "anthropic_api_key": None}
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
    response = client.post("/api/v1/channels", json={"name": "Space Facts", "niche": "astronomy"})
    assert response.status_code == 201
    return response.json()


SCRIPT_RESPONSE = {
    "hook": "This planet rains diamonds.",
    "scenes": [
        {
            "narration": "Neptune is so cold and so pressurised that carbon may crystallise.",
            "visual": "Neptune",
            "duration_seconds": 6,
        },
        {
            "narration": "Scientists think diamonds could sink through its atmosphere.",
            "visual": "Falling gems",
            "duration_seconds": 5,
        },
    ],
    "call_to_action": "Follow for more space facts.",
}

METADATA_RESPONSE = {
    "title": "It Rains Diamonds on Neptune",
    "description": "Why Neptune may have diamond rain. #Shorts",
    "tags": ["neptune", "space", "#Space", "diamond rain"],
    "hashtags": ["Shorts", "#space"],
    "thumbnail_text": "DIAMOND RAIN",
    "thumbnail_prompt": "Blue planet with glittering diamonds falling",
}
