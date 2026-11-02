import copy

from tests.conftest import METADATA_RESPONSE, SCRIPT_RESPONSE, StubAIProvider
from tests.helpers import create_project


def test_script_generation_without_claude_key_returns_503(client, channel):
    project = create_project(client, channel["id"])
    response = client.post(f"/api/v1/projects/{project['id']}/scripts/generate")
    assert response.status_code == 503
    assert response.json()["error"] == "integration_not_configured"
    assert client.get(f"/api/v1/projects/{project['id']}").json()["status"] == "draft"


def test_script_generation_stores_versions(make_client, channel):
    ai = StubAIProvider([SCRIPT_RESPONSE, SCRIPT_RESPONSE])
    client = make_client(ai=ai)
    project = create_project(client, channel["id"])
    first = client.post(f"/api/v1/projects/{project['id']}/scripts/generate")
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["version"] == 1
    assert body["provider"] == "stub"
    assert body["full_text"].endswith("Follow for more space facts.")
    assert body["estimated_duration_seconds"] >= 11
    assert "vertical YouTube Short" in ai.calls[0]["prompt"]
    assert "astronomy" in ai.calls[0]["prompt"]

    second = client.post(f"/api/v1/projects/{project['id']}/scripts/generate").json()
    assert second["version"] == 2
    assert client.get(f"/api/v1/projects/{project['id']}").json()["status"] == "script_ready"
    assert len(client.get(f"/api/v1/projects/{project['id']}/scripts").json()) == 2


def test_long_form_prompt(make_client, channel):
    ai = StubAIProvider([SCRIPT_RESPONSE])
    client = make_client(ai=ai)
    project = create_project(client, channel["id"], format="long")
    client.post(f"/api/v1/projects/{project['id']}/scripts/generate")
    assert "long-form" in ai.calls[0]["prompt"]


def test_overlong_short_is_rejected(make_client, channel):
    too_long = copy.deepcopy(SCRIPT_RESPONSE)
    too_long["scenes"][0]["duration_seconds"] = 400
    client = make_client(ai=StubAIProvider([too_long]))
    project = create_project(client, channel["id"])
    response = client.post(f"/api/v1/projects/{project['id']}/scripts/generate")
    assert response.status_code == 502
    assert client.get(f"/api/v1/projects/{project['id']}").json()["status"] == "draft"


def test_invalid_ai_output_is_rejected(make_client, channel):
    client = make_client(ai=StubAIProvider([{"hook": "x", "scenes": [], "call_to_action": ""}]))
    project = create_project(client, channel["id"])
    assert client.post(f"/api/v1/projects/{project['id']}/scripts/generate").status_code == 502


def test_metadata_generation(make_client, channel):
    client = make_client(ai=StubAIProvider([SCRIPT_RESPONSE, METADATA_RESPONSE]))
    project = create_project(client, channel["id"])
    assert client.post(f"/api/v1/projects/{project['id']}/metadata/generate").status_code == 409  # no script yet
    client.post(f"/api/v1/projects/{project['id']}/scripts/generate")
    response = client.post(f"/api/v1/projects/{project['id']}/metadata/generate")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["tags"] == ["neptune", "space", "diamond rain"]  # de-duplicated, '#' stripped
    assert body["hashtags"] == ["#Shorts", "#space"]
    assert client.get(f"/api/v1/projects/{project['id']}").json()["status"] == "metadata_ready"
