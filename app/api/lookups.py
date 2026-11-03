import uuid

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Channel, VideoProject


def get_channel_or_404(db: Session, channel_id: uuid.UUID) -> Channel:
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise NotFoundError(f"Channel {channel_id} not found.")
    return channel


def get_project_or_404(db: Session, project_id: uuid.UUID) -> VideoProject:
    project = db.get(VideoProject, project_id)
    if project is None:
        raise NotFoundError(f"Project {project_id} not found.")
    return project
