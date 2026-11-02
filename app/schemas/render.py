import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import JobStatus
from app.schemas.common import ORMModel


class RenderJobCreate(BaseModel):
    script_id: uuid.UUID | None = None  # defaults to the latest script


class RenderJobRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    script_id: uuid.UUID | None
    status: JobStatus
    width: int
    height: int
    fps: int
    output_path: str | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
