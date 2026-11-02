import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models._types import enum_column
from app.models.enums import AnalyticsSource


class AnalyticsSnapshot(UUIDPrimaryKeyMixin, Base):
    """Cumulative metrics for one video at one point in time.

    Field names mirror YouTube Analytics API metrics so the future collector
    can write rows without translation.
    """

    __tablename__ = "analytics_snapshots"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    source: Mapped[AnalyticsSource] = mapped_column(enum_column(AnalyticsSource), nullable=False)
    views: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    impressions: Mapped[int | None] = mapped_column(BigInteger)
    impressions_ctr: Mapped[float | None] = mapped_column(Float)  # 0..1
    estimated_minutes_watched: Mapped[float | None] = mapped_column(Float)
    average_view_duration_seconds: Mapped[float | None] = mapped_column(Float)
    average_view_percentage: Mapped[float | None] = mapped_column(Float)  # 0..100
    likes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shares: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    subscribers_gained: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    project: Mapped["VideoProject"] = relationship(back_populates="analytics_snapshots")  # noqa: F821
