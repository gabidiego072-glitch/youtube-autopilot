import pytest
from pydantic import SecretStr

from tests.conftest import make_settings


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_checks_database(client):
    assert client.get("/health/ready").json() == {"status": "ready", "database": "ok"}


def test_production_requires_postgres_and_api_key():
    with pytest.raises(ValueError, match="PostgreSQL"):
        make_settings(environment="production", api_key="secret")
    with pytest.raises(ValueError, match="API_KEY"):
        make_settings(environment="production", database_url="postgresql+psycopg://u:p@h/db")
    ok = make_settings(environment="production", database_url="postgresql+psycopg://u:p@h/db", api_key="s")
    assert ok.environment == "production"


def test_integration_flags_reflect_credentials():
    settings = make_settings()
    assert not settings.claude_configured
    assert not settings.youtube_configured
    assert not settings.youtube_publishing_enabled
    configured = make_settings(
        anthropic_api_key=SecretStr("k"),
        youtube_client_id="a",
        youtube_client_secret="b",
        youtube_refresh_token="c",
    )
    assert configured.claude_configured and configured.youtube_configured


def test_api_key_required_when_configured(make_client):
    client = make_client(make_settings(api_key="top-secret"))
    assert client.get("/api/v1/channels").status_code == 401
    assert client.get("/api/v1/channels", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/v1/channels", headers={"X-API-Key": "top-secret"}).status_code == 200
    assert client.get("/health").status_code == 200  # probes stay open


def test_integrations_status_is_honest(client):
    body = client.get("/api/v1/system/integrations").json()
    assert body["claude"]["configured"] is False
    # Implemented, but not configured: no credentials means nothing can be uploaded or read.
    assert body["youtube_data_api"] == {**body["youtube_data_api"], "implemented": True, "configured": False}
    assert body["youtube_analytics_api"]["configured"] is False
    assert body["publishing_enabled"] is False
    assert "ai_images" not in body and "ai_video" not in body  # everything is rendered by code
    assert body["voice"]["configured"] is False


def test_empty_wikipedia_user_agent_falls_back_to_the_default():
    # GitHub passes an unset repository variable as an empty string; Wikimedia answers 403 to an empty agent.
    assert make_settings(wikipedia_user_agent="").wikipedia_user_agent.startswith("YouTubeAutopilot/")
