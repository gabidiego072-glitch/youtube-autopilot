import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AssetKind, ContentCategory, FactCheckStatus, IdeaStatus, VideoFormat
from app.schemas.common import ORMModel


class IdeaGenerateRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=30)
    focus: str | None = Field(default=None, max_length=300)


class IdeaRead(ORMModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    premise: str
    category: ContentCategory
    hook: str
    angle: str
    science_basis: str
    scores: dict
    score: float
    status: IdeaStatus
    project_id: uuid.UUID | None
    created_at: datetime


class IdeaSelectRequest(BaseModel):
    format: VideoFormat
    target_duration_seconds: int | None = Field(default=None, gt=0)


class ResearchRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    concepts: list[dict]
    sources: list[dict]
    key_facts: list[dict]
    status: str
    created_at: datetime


class FactCheckRead(BaseModel):
    script_id: uuid.UUID
    status: FactCheckStatus
    verdicts: list[dict]
    summary: str


class VisualsRequest(BaseModel):
    aspect: str | None = Field(default=None, pattern=r"^(9:16|16:9)$")  # default: from the project format
    animate: bool = True  # use the AI video provider when one is configured


class AssetRead(ORMModel):
    id: uuid.UUID
    kind: AssetKind
    uri: str
    scene_index: int | None
    script_id: uuid.UUID | None
    provider: str | None
    size_bytes: int | None
    created_at: datetime


class AssembleRequest(BaseModel):
    music_path: str | None = None  # optional local file (royalty-free music)
    subtitles: bool = True
