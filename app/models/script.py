import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, UUIDPrimaryKeyMixin, utcnow


class Script(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scripts"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_scripts_project_version"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False)
    # List of {"narration": str, "visual": str, "duration_seconds": float}
    scenes: Mapped[list[dict]] = mapped_column(JSONType, nullable=False)
    call_to_action: Mapped[str | None] = mapped_column(Text)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_duration_seconds: Mapped[float] = mapped_column(nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )

    project: Mapped["VideoProject"] = relationship(back_populates="scripts")  # noqa: F821
