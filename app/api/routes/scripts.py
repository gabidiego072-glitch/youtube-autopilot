import uuid

from fastapi import APIRouter, status

from app.api.deps import AIProviderDep, DbSession, SettingsDep
from app.api.lookups import get_project_or_404
from app.core.errors import InvalidStateTransitionError
from app.models import Script
from app.models.enums import ProjectStatus
from app.schemas.project import ScriptRead
from app.services.production.formats import get_format_spec
from app.services.production.pipeline import can_transition, transition
from app.services.scripts.generator import generate_script

router = APIRouter(prefix="/projects/{project_id}/scripts", tags=["scripts"])


@router.post("/generate", response_model=ScriptRead, status_code=status.HTTP_201_CREATED)
def generate(project_id: uuid.UUID, db: DbSession, settings: SettingsDep, ai: AIProviderDep) -> Script:
    """Generate a new script version with the configured AI provider (Claude)."""
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
    )
    script = Script(
        project_id=project.id,
        version=len(project.scripts) + 1,
        hook=draft.hook,
        scenes=[scene.model_dump() for scene in draft.scenes],
        call_to_action=draft.call_to_action,
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
