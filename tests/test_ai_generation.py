import copy

from tests.conftest import FACTCHECK_PASS, METADATA_RESPONSE, SCRIPT_RESPONSE, StubAIProvider
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
    assert body["title_question"].startswith("¿Qué pasaría si")
    assert body["ending_type"] == "question"
    assert body["call_to_action"] == "¿Tú dónde vivirías?"
    assert body["full_text"].endswith("¿Tú dónde vivirías?")
    assert body["fact_check_status"] == "not_checked"
    assert body["visual_bible"]["recurring_subjects"][0]["name"] == "The narrator"
    assert body["scenes"][1]["claims"][0]["type"] == "established"
    prompt = ai.calls[0]["prompt"]
    assert "vertical YouTube Short" in prompt and "ciencia hipotética" in prompt
    assert "No research notes" in prompt  # no research brief yet
    assert "What would happen if" in ai.calls[0]["system"]

    second = client.post(f"/api/v1/projects/{project['id']}/scripts/generate").json()
    assert second["version"] == 2
    assert client.get(f"/api/v1/projects/{project['id']}").json()["status"] == "script_ready"
    assert len(client.get(f"/api/v1/projects/{project['id']}/scripts").json()) == 2


def test_long_form_prompt(make_client, channel):
    ai = StubAIProvider([SCRIPT_RESPONSE] * 2)  # too few escalations for long form -> one retry
    client = make_client(ai=ai)
    project = create_project(client, channel["id"], format="long")
    client.post(f"/api/v1/projects/{project['id']}/scripts/generate")
    assert "long-form" in ai.calls[0]["prompt"]


def test_overlong_short_is_rejected(make_client, channel):
    too_long = copy.deepcopy(SCRIPT_RESPONSE)
    too_long["scenes"][1]["duration_seconds"] = 400
    client = make_client(ai=StubAIProvider([too_long] * 2))
    project = create_project(client, channel["id"])
    response = client.post(f"/api/v1/projects/{project['id']}/scripts/generate")
    assert response.status_code == 502
    assert client.get(f"/api/v1/projects/{project['id']}").json()["status"] == "draft"


def test_invalid_ai_output_is_rejected(make_client, channel):
    client = make_client(ai=StubAIProvider([{"hook": "x", "scenes": []}] * 2))
    project = create_project(client, channel["id"])
    assert client.post(f"/api/v1/projects/{project['id']}/scripts/generate").status_code == 502


def test_script_gets_one_retry_with_the_reasons(make_client, channel):
    bad = copy.deepcopy(SCRIPT_RESPONSE)
    bad["hook"] = "uno dos tres cuatro cinco seis siete ocho nueve diez"
    ai = StubAIProvider([bad, SCRIPT_RESPONSE])
    client = make_client(ai=ai)
    project = create_project(client, channel["id"])
    assert client.post(f"/api/v1/projects/{project['id']}/scripts/generate").status_code < 300
    assert len(ai.calls) == 2 and "Hook is longer" in ai.calls[1]["prompt"]


def test_question_ending_missing_its_mark_is_repaired():
    from app.services.scripts.generator import ScriptDraft, repair_ending

    data = copy.deepcopy(SCRIPT_RESPONSE)
    data.update(ending_type="question", ending_line="¿Tú qué harías")
    data["scenes"][-1]["narration"] = "Y ahora... ¿Tú qué harías"
    draft = ScriptDraft(**data, provider="p", model="m")
    repair_ending(draft)
    assert draft.ending_line == "¿Tú qué harías?" and draft.scenes[-1].narration.endswith("harías?")


def test_fact_check_flow(make_client, channel):
    failing = copy.deepcopy(FACTCHECK_PASS)
    failing["verdicts"][2]["verdict"] = "mislabeled"
    client = make_client(ai=StubAIProvider([SCRIPT_RESPONSE, failing, FACTCHECK_PASS]))
    project = create_project(client, channel["id"])
    script = client.post(f"/api/v1/projects/{project['id']}/scripts/generate").json()
    url = f"/api/v1/projects/{project['id']}/scripts/{script['id']}/fact-check"
    first = client.post(url).json()
    assert first["status"] == "needs_revision"
    assert client.post(url).json()["status"] == "passed"
    assert client.get(url).json()["status"] == "passed"


def test_metadata_generation(make_client, channel):
    ai = StubAIProvider([SCRIPT_RESPONSE, METADATA_RESPONSE])
    client = make_client(ai=ai)
    project = create_project(client, channel["id"])
    assert client.post(f"/api/v1/projects/{project['id']}/metadata/generate").status_code == 409  # no script yet
    client.post(f"/api/v1/projects/{project['id']}/scripts/generate")
    response = client.post(f"/api/v1/projects/{project['id']}/metadata/generate")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["tags"] == ["rotación terrestre", "ciencia", "qué pasaría si"]  # de-duplicated, '#' stripped
    assert body["hashtags"] == ["#Shorts", "#ciencia"]
    assert body["pinned_comment"] == "¿Tú dónde vivirías?"
    assert body["category_id"] == "28"
    assert "¿Tú dónde vivirías?" in ai.calls[1]["prompt"]
    assert client.get(f"/api/v1/projects/{project['id']}").json()["status"] == "metadata_ready"
