import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models._types import enum_column
from app.models.enums import ContentCategory, ProjectStatus, VideoFormat


class VideoProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One video moving through the pipeline. Shorts and long-form share this table."""

    __tablename__ = "video_projects"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True, nullable=False
    )
    working_title: Mapped[str] = mapped_column(String(200), nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[VideoFormat] = mapped_column(enum_column(VideoFormat), nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        enum_column(ProjectStatus), default=ProjectStatus.DRAFT, nullable=False, index=True
    )
    target_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[ContentCategory | None] = mapped_column(enum_column(ContentCategory), index=True)
    idea_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ideas.id", ondelete="SET NULL", use_alter=True))
    language: Mapped[str] = mapped_column(String(16), default="es", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    youtube_video_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    channel: Mapped["Channel"] = relationship(back_populates="projects")  # noqa: F821
    scripts: Mapped[list["Script"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan", order_by="Script.version"
    )
    research_briefs: Mapped[list["ResearchBrief"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan", order_by="ResearchBrief.created_at"
    )
    render_jobs: Mapped[list["RenderJob"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    metadata_versions: Mapped[list["VideoMetadata"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan", order_by="VideoMetadata.version"
    )
    assets: Mapped[list["MediaAsset"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    publish_jobs: Mapped[list["PublishJob"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    analytics_snapshots: Mapped[list["AnalyticsSnapshot"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan", order_by="AnalyticsSnapshot.captured_at"
    )
