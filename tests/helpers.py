def create_project(client, channel_id: str, **overrides) -> dict:
    payload = {
        "channel_id": channel_id,
        "working_title": "Diamond rain",
        "topic": "Diamond rain on Neptune",
        "format": "short",
    }
    response = client.post("/api/v1/projects", json={**payload, **overrides})
    assert response.status_code == 201, response.text
    return response.json()
