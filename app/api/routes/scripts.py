import uuid

from fastapi import APIRouter, status

from app.api.deps import AIProviderDep, DbSession, SettingsDep
from app.api.lookups import get_project_or_404
from app.core.errors import InvalidStateTransitionError, NotFoundError
from app.models import Script
from app.models.enums import FactCheckStatus, ProjectStatus
from app.schemas.content import FactCheckRead
from app.schemas.project import ScriptRead
from app.services.factcheck.checker import fact_check
from app.services.production.formats import get_format_spec
from app.services.production.pipeline import can_transition, transition
from app.services.scripts.generator import generate_script

router = APIRouter(prefix="/projects/{project_id}/scripts", tags=["scripts"])


@router.post("/generate", response_model=ScriptRead, status_code=status.HTTP_201_CREATED)
def generate(project_id: uuid.UUID, db: DbSession, settings: SettingsDep, ai: AIProviderDep) -> Script:
    """Write a new 'What would happen if...?' script version, grounded in the latest research brief."""
    project = get_project_or_404(db, project_id)
    if not can_transition(project.status, ProjectStatus.SCRIPT_READY):
        raise InvalidStateTransitionError(f"Cannot generate a script while project is '{project.status.value}'.")

    draft = generate_script(
        ai,
        spec=get_format_spec(project.format, settings),
        topic=project.topic,
        working_title=project.working_title,
        target_duration_seconds=project.target_duration_seconds,
        language=project.language,
        niche=project.channel.niche,
        style_guide=project.channel.style_guide,
        notes=project.notes,
        research=_latest_research(project),
    )
    script = Script(
        project_id=project.id,
        version=len(project.scripts) + 1,
        title_question=draft.title_question,
        hook=draft.hook,
        scenes=[scene.model_dump(mode="json") for scene in draft.scenes],
        call_to_action=draft.call_to_action,
        ending_type=draft.ending_type,
        visual_bible=draft.visual_bible.model_dump(),
        full_text=draft.full_text,
        estimated_duration_seconds=draft.estimated_duration_seconds,
        provider=draft.provider,
        model=draft.model,
        prompt_version=draft.prompt_version,
    )
    db.add(script)
    transition(project, ProjectStatus.SCRIPT_READY)
    db.commit()
    db.refresh(script)
    return script


@router.get("", response_model=list[ScriptRead])
def list_scripts(project_id: uuid.UUID, db: DbSession) -> list[Script]:
    return get_project_or_404(db, project_id).scripts


def _latest_research(project) -> dict | None:
    if not project.research_briefs:
        return None
    brief = project.research_briefs[-1]
    return {"sources": brief.sources, "key_facts": brief.key_facts}


@router.post("/{script_id}/fact-check", response_model=FactCheckRead)
def check_script(project_id: uuid.UUID, script_id: uuid.UUID, db: DbSession, ai: AIProviderDep) -> FactCheckRead:
    """AI science review of every labelled claim. Approval requires status 'passed'."""
    project = get_project_or_404(db, project_id)
    script = db.get(Script, script_id)
    if script is None or script.project_id != project.id:
        raise NotFoundError("Script not found for this project.")
    result = fact_check(ai, premise=project.working_title, scenes=script.scenes, research=_latest_research(project))
    script.fact_check_status = result.status
    script.fact_check = result.as_record()
    db.commit()
    return FactCheckRead(script_id=script.id, status=result.status, verdicts=result.verdicts, summary=result.summary)


@router.get("/{script_id}/fact-check", response_model=FactCheckRead)
def get_fact_check(project_id: uuid.UUID, script_id: uuid.UUID, db: DbSession) -> FactCheckRead:
    script = db.get(Script, script_id)
    if script is None or script.project_id != project_id:
        raise NotFoundError("Script not found for this project.")
    record = script.fact_check or {}
    return FactCheckRead(
        script_id=script.id,
        status=script.fact_check_status or FactCheckStatus.NOT_CHECKED,
        verdicts=record.get("verdicts", []),
        summary=record.get("summary", ""),
    )
