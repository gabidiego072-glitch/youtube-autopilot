import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, UUIDPrimaryKeyMixin, utcnow
from app.models._types import enum_column
from app.models.enums import ContentCategory, IdeaStatus


class Idea(UUIDPrimaryKeyMixin, Base):
    """A candidate 'What would happen if...?' premise, scored before it becomes a project."""

    __tablename__ = "ideas"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True, nullable=False
    )
    premise: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[ContentCategory] = mapped_column(enum_column(ContentCategory), nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False)
    angle: Mapped[str] = mapped_column(Text, nullable=False)
    science_basis: Mapped[str] = mapped_column(Text, nullable=False)
    # {"curiosity": 0-10, "visual_potential": 0-10, "scientific_grounding": 0-10, "evergreen": 0-10}
    scores: Mapped[dict] = mapped_column(JSONType, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    status: Mapped[IdeaStatus] = mapped_column(enum_column(IdeaStatus), default=IdeaStatus.NEW, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("video_projects.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
