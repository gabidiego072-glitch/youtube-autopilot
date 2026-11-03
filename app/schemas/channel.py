import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    niche: str | None = Field(default=None, max_length=200)
    language: str = Field(default="es", max_length=16)
    description: str | None = None
    style_guide: str | None = None


class ChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    niche: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default=None, max_length=16)
    description: str | None = None
    style_guide: str | None = None


class ChannelRead(ORMModel):
    id: uuid.UUID
    name: str
    youtube_channel_id: str | None
    niche: str | None
    language: str
    description: str | None
    style_guide: str | None
    created_at: datetime
    updated_at: datetime
