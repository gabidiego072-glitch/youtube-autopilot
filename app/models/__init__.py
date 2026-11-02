"""Import every model so `Base.metadata` is complete (used by Alembic and tests)."""

from app.db.base import Base
from app.models.analytics import AnalyticsSnapshot
from app.models.asset import MediaAsset
from app.models.channel import Channel
from app.models.insight import Insight
from app.models.metadata import VideoMetadata
from app.models.publish_job import PublishJob
from app.models.render_job import RenderJob
from app.models.report import Report
from app.models.script import Script
from app.models.video_project import VideoProject

__all__ = [
    "AnalyticsSnapshot",
    "Base",
    "Channel",
    "Insight",
    "MediaAsset",
    "PublishJob",
    "RenderJob",
    "Report",
    "Script",
    "VideoMetadata",
    "VideoProject",
]
