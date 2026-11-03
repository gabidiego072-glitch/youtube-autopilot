import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models._types import enum_column
from app.models.enums import PrivacyStatus, PublishStatus


class PublishJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "publish_jobs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metadata_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("video_metadata.id", ondelete="SET NULL"))
    status: Mapped[PublishStatus] = mapped_column(
        enum_column(PublishStatus), default=PublishStatus.PENDING, nullable=False
    )
    privacy: Mapped[PrivacyStatus] = mapped_column(
        enum_column(PrivacyStatus), default=PrivacyStatus.PRIVATE, nullable=False
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    youtube_video_id: Mapped[str | None] = mapped_column(String(32))
    error: Mapped[str | None] = mapped_column(Text)

    project: Mapped["VideoProject"] = relationship(back_populates="publish_jobs")  # noqa: F821
