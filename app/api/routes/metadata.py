import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AIProviderDep, DbSession
from app.api.lookups import get_project_or_404
from app.core.errors import InvalidStateTransitionError
from app.models import VideoMetadata
from app.models.enums import ProjectStatus
from app.schemas.project import MetadataRead
from app.services.metadata.generator import generate_metadata
from app.services.production.pipeline import can_transition, transition

router = APIRouter(prefix="/projects/{project_id}/metadata", tags=["metadata"])


@router.post("/generate", response_model=MetadataRead, status_code=status.HTTP_201_CREATED)
def generate(project_id: uuid.UUID, db: DbSession, ai: AIProviderDep) -> VideoMetadata:
    """Generate title, description, tags and a thumbnail concept from the latest script."""
    project = get_project_or_404(db, project_id)
    if not project.scripts:
        raise HTTPException(status_code=409, detail="Generate a script first.")
    if not can_transition(project.status, ProjectStatus.METADATA_READY):
        raise InvalidStateTransitionError(f"Cannot generate metadata while project is '{project.status.value}'.")
    script = project.scripts[-1]
    draft = generate_metadata(
        ai,
        video_format=project.format,
        working_title=script.title_question or project.working_title,
        script_text=script.full_text,
        language=project.language,
        ending_line=script.call_to_action,
        sources=project.research_briefs[-1].sources if project.research_briefs else None,
    )
    metadata = VideoMetadata(
        project_id=project.id,
        version=len(project.metadata_versions) + 1,
        **draft.model_dump(),
    )
    db.add(metadata)
    transition(project, ProjectStatus.METADATA_READY)
    db.commit()
    db.refresh(metadata)
    return metadata


@router.get("", response_model=list[MetadataRead])
def list_metadata(project_id: uuid.UUID, db: DbSession) -> list[VideoMetadata]:
    return get_project_or_404(db, project_id).metadata_versions
