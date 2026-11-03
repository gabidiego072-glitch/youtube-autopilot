from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Channel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "channels"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Filled in once the YouTube integration links a real channel.
    youtube_channel_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    niche: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(16), default="es", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Free-form brand/voice guidance passed to the script generator.
    style_guide: Mapped[str | None] = mapped_column(Text)

    projects: Mapped[list["VideoProject"]] = relationship(  # noqa: F821
        back_populates="channel", cascade="all, delete-orphan"
    )
