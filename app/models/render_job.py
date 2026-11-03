import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models._types import enum_column
from app.models.enums import JobStatus


class RenderJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "render_jobs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    script_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scripts.id", ondelete="SET NULL"))
    status: Mapped[JobStatus] = mapped_column(
        enum_column(JobStatus), default=JobStatus.QUEUED, nullable=False, index=True
    )
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    fps: Mapped[int] = mapped_column(Integer, nullable=False)
    output_path: Mapped[str | None] = mapped_column(String(1024))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped["VideoProject"] = relationship(back_populates="render_jobs")  # noqa: F821
