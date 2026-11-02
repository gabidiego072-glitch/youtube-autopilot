import uuid

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models._types import enum_column
from app.models.enums import AssetKind


class MediaAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A file used or produced by the pipeline (local path or storage URI)."""

    __tablename__ = "media_assets"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("video_projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[AssetKind] = mapped_column(enum_column(AssetKind), nullable=False)
    uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    scene_index: Mapped[int | None] = mapped_column(Integer)  # which script scene it belongs to
    script_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scripts.id", ondelete="SET NULL"))
    provider: Mapped[str | None] = mapped_column(String(32))

    project: Mapped["VideoProject"] = relationship(back_populates="assets")  # noqa: F821
