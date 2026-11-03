from tests.helpers import create_project


def test_channel_crud(client):
    created = client.post("/api/v1/channels", json={"name": "Chan", "language": "es"}).json()
    assert created["language"] == "es"
    assert client.get(f"/api/v1/channels/{created['id']}").json()["name"] == "Chan"
    updated = client.patch(f"/api/v1/channels/{created['id']}", json={"niche": "history"}).json()
    assert updated["niche"] == "history"
    assert len(client.get("/api/v1/channels").json()) == 1
    assert client.delete(f"/api/v1/channels/{created['id']}").status_code == 204
    missing = client.get(f"/api/v1/channels/{created['id']}")
    assert missing.status_code == 404
    assert missing.json()["error"] == "not_found"


def test_short_project_defaults(client, channel):
    project = create_project(client, channel["id"])
    assert project["format"] == "short"
    assert project["status"] == "draft"
    assert project["target_duration_seconds"] == 45
    assert project["language"] == "es"  # inherited from channel (Spanish by default)


def test_long_project_defaults(client, channel):
    project = create_project(client, channel["id"], format="long")
    assert project["target_duration_seconds"] == 480


def test_duration_limits_per_format(client, channel):
    base = {"channel_id": channel["id"], "working_title": "t", "topic": "t"}
    too_long_short = client.post("/api/v1/projects", json={**base, "format": "short", "target_duration_seconds": 600})
    assert too_long_short.status_code == 422
    too_short_long = client.post("/api/v1/projects", json={**base, "format": "long", "target_duration_seconds": 60})
    assert too_short_long.status_code == 422


def test_project_requires_existing_channel(client):
    response = client.post(
        "/api/v1/projects",
        json={
            "channel_id": "00000000-0000-0000-0000-000000000000",
            "working_title": "t",
            "topic": "t",
            "format": "short",
        },
    )
    assert response.status_code == 404


def test_list_projects_filters(client, channel):
    create_project(client, channel["id"], format="short")
    create_project(client, channel["id"], format="long")
    assert len(client.get("/api/v1/projects").json()) == 2
    shorts = client.get("/api/v1/projects", params={"format": "short"}).json()
    assert [p["format"] for p in shorts] == ["short"]


def test_archive_then_no_further_transitions(client, channel):
    project = create_project(client, channel["id"])
    assert client.post(f"/api/v1/projects/{project['id']}/archive").json()["status"] == "archived"
    again = client.post(f"/api/v1/projects/{project['id']}/archive")
    assert again.status_code == 409
    assert again.json()["error"] == "invalid_state_transition"
