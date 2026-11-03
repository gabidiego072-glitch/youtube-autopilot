import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin
from app.models._types import enum_column
from app.models.enums import RunStatus, VideoFormat


class PipelineRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One autonomous production: topic -> research -> script -> ... -> (approval) -> publish.

    Every step records its status, attempts, timing, error and token usage, so a run can be
    resumed from the step that failed and audited afterwards.
    """

    __tablename__ = "pipeline_runs"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("video_projects.id", ondelete="SET NULL"))
    format: Mapped[VideoFormat] = mapped_column(enum_column(VideoFormat), nullable=False)
    render_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    status: Mapped[RunStatus] = mapped_column(
        enum_column(RunStatus), default=RunStatus.QUEUED, server_default="queued", nullable=False, index=True
    )
    current_step: Mapped[str | None] = mapped_column(String(32))
    # [{"name", "status", "attempts", "started_at", "finished_at", "error", "detail"}]
    steps: Mapped[list[dict]] = mapped_column(JSONType, nullable=False, default=list)
    # {"input_tokens", "output_tokens", "by_step": {step: {...}}}
    usage: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    auto_publish: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
