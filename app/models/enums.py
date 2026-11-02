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


class ContentCategory(enum.StrEnum):
    HUMAN_BODY = "human_body"
    SCALE_AND_SIZE = "scale_and_size"
    SPEED_AND_MOTION = "speed_and_motion"
    EARTH_AND_CLIMATE = "earth_and_climate"
    SPACE_AND_ASTRONOMY = "space_and_astronomy"
    PHYSICS_LAWS = "physics_laws"
    TIME_AND_LIFESPAN = "time_and_lifespan"
    NATURE_AND_ANIMALS = "nature_and_animals"
    SOCIETY_AND_TECHNOLOGY = "society_and_technology"


class IdeaStatus(enum.StrEnum):
    NEW = "new"
    USED = "used"
    REJECTED = "rejected"


class ClaimType(enum.StrEnum):
    ESTABLISHED = "established"
    ESTIMATE = "estimate"
    SPECULATION = "speculation"


class FactCheckStatus(enum.StrEnum):
    NOT_CHECKED = "not_checked"
    PASSED = "passed"
    NEEDS_REVISION = "needs_revision"
