import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.api.lookups import get_channel_or_404
from app.core.errors import NotFoundError
from app.models import Report
from app.schemas.analytics import ReportCreate, ReportRead
from app.services.reporting.builder import build_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
def create_report(payload: ReportCreate, db: DbSession) -> Report:
    if payload.period_end <= payload.period_start:
        raise HTTPException(status_code=422, detail="period_end must be after period_start.")
    if payload.channel_id is not None:
        get_channel_or_404(db, payload.channel_id)
    content = build_report(
        db, period_start=payload.period_start, period_end=payload.period_end, channel_id=payload.channel_id
    )
    report = Report(**payload.model_dump(), content=content)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("", response_model=list[ReportRead])
def list_reports(db: DbSession, limit: int = 50) -> list[Report]:
    return list(db.scalars(select(Report).order_by(Report.created_at.desc()).limit(min(limit, 500))))


@router.get("/{report_id}", response_model=ReportRead)
def get_report(report_id: uuid.UUID, db: DbSession) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise NotFoundError(f"Report {report_id} not found.")
    return report
