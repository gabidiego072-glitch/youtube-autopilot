import uuid

from fastapi import APIRouter, status

from app.api.deps import AIProviderDep, DbSession, WikipediaDep
from app.api.lookups import get_project_or_404
from app.models import ResearchBrief
from app.schemas.content import ResearchRead
from app.services.research.briefing import build_brief

router = APIRouter(prefix="/projects/{project_id}/research", tags=["research"])


@router.post("", response_model=ResearchRead, status_code=status.HTTP_201_CREATED)
def research(project_id: uuid.UUID, db: DbSession, ai: AIProviderDep, wiki: WikipediaDep) -> ResearchBrief:
    """Find the real science behind the premise (free Wikipedia sources) before writing."""
    project = get_project_or_404(db, project_id)
    brief = build_brief(ai, wiki, premise=project.working_title, language=project.language)
    record = ResearchBrief(
        project_id=project.id,
        concepts=brief.concepts,
        sources=brief.sources,
        key_facts=brief.key_facts,
        status=brief.status,
        provider=brief.provider,
        model=brief.model,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("", response_model=list[ResearchRead])
def list_research(project_id: uuid.UUID, db: DbSession) -> list[ResearchBrief]:
    return get_project_or_404(db, project_id).research_briefs
