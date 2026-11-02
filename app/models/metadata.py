import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, UUIDPrimaryKeyMixin, utcnow


class VideoMetadata(UUIDPrimaryKeyMixin, Base):
    """Title, description, tags and thumbnail concept for one upload."""

    __tablename__ = "video_metadata"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_video_metadata_project_version"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    hashtags: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    thumbnail_text: Mapped[str | None] = mapped_column(String(100))
    thumbnail_prompt: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[str | None] = mapped_column(String(8))
    # Comment the channel pins to start the discussion (usually the ending question).
    pinned_comment: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )

    project: Mapped["VideoProject"] = relationship(back_populates="metadata_versions")  # noqa: F821
