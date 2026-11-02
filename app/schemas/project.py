import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ProjectStatus, VideoFormat
from app.schemas.common import ORMModel


class ProjectCreate(BaseModel):
    channel_id: uuid.UUID
    working_title: str = Field(min_length=1, max_length=200)
    topic: str = Field(min_length=1)
    format: VideoFormat
    target_duration_seconds: int | None = Field(default=None, gt=0)
    language: str | None = Field(default=None, max_length=16)
    notes: str | None = None


class ProjectUpdate(BaseModel):
    working_title: str | None = Field(default=None, min_length=1, max_length=200)
    topic: str | None = Field(default=None, min_length=1)
    target_duration_seconds: int | None = Field(default=None, gt=0)
    notes: str | None = None


class ProjectRead(ORMModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    working_title: str
    topic: str
    format: VideoFormat
    status: ProjectStatus
    target_duration_seconds: int
    language: str
    notes: str | None
    youtube_video_id: str | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ScriptRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    version: int
    hook: str
    scenes: list[dict]
    call_to_action: str | None
    full_text: str
    estimated_duration_seconds: float
    provider: str
    model: str
    prompt_version: str
    created_at: datetime


class MetadataRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    version: int
    title: str
    description: str
    tags: list[str]
    hashtags: list[str]
    thumbnail_text: str | None
    thumbnail_prompt: str | None
    category_id: str | None
    provider: str
    model: str
    created_at: datetime
