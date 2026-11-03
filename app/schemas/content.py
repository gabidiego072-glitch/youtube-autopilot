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


class SceneRenderRequest(BaseModel):
    mode: str | None = Field(default=None, pattern=r"^(preview|draft|final)$")  # default: SCENE_RENDER_QUALITY
    scale: float | None = Field(default=None, gt=0, le=1)  # override resolution (fraction of 1080p)
    samples: int | None = Field(default=None, ge=1, le=512)


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
    mode: str = Field(default="draft", pattern=r"^(preview|draft|final)$")
    music_path: str | None = None  # optional own music file; default: generated ambient music
    subtitles: bool = True
