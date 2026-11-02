import enum


class VideoFormat(enum.StrEnum):
    SHORT = "short"
    LONG = "long"


class ProjectStatus(enum.StrEnum):
    DRAFT = "draft"
    SCRIPT_READY = "script_ready"
    RENDERING = "rendering"
    RENDERED = "rendered"
    METADATA_READY = "metadata_ready"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHED = "published"
    FAILED = "failed"
    ARCHIVED = "archived"


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PublishStatus(enum.StrEnum):
    PENDING = "pending"
    UPLOADING = "uploading"
    PUBLISHED = "published"
    FAILED = "failed"


class PrivacyStatus(enum.StrEnum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"


class AssetKind(enum.StrEnum):
    VOICEOVER = "voiceover"
    MUSIC = "music"
    IMAGE = "image"
    VIDEO_CLIP = "video_clip"
    SUBTITLES = "subtitles"
    THUMBNAIL = "thumbnail"
    RENDER_OUTPUT = "render_output"


class AnalyticsSource(enum.StrEnum):
    MANUAL = "manual"
    YOUTUBE_ANALYTICS = "youtube_analytics"


class ReportType(enum.StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"
