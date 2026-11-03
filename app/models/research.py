import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, UUIDPrimaryKeyMixin, utcnow


class ResearchBrief(UUIDPrimaryKeyMixin, Base):
    """Background facts gathered for a premise before the script is written."""

    __tablename__ = "research_briefs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # [{"concept": str, "why": str}]
    concepts: Mapped[list[dict]] = mapped_column(JSONType, nullable=False)
    # [{"title": str, "url": str, "extract": str, "source": "wikipedia"}]
    sources: Mapped[list[dict]] = mapped_column(JSONType, nullable=False)
    # [{"fact": str, "type": "established|estimate", "source_url": str | None}]
    key_facts: Mapped[list[dict]] = mapped_column(JSONType, nullable=False)
    # complete: every concept found a source; partial: some lookups failed
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )

    project: Mapped["VideoProject"] = relationship(back_populates="research_briefs")  # noqa: F821
