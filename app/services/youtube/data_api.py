"""YouTube Data API v3 publisher.

Not implemented yet (roadmap Phase 5). It refuses to run, in this order:
1. publishing disabled (YOUTUBE_PUBLISHING_ENABLED=false, the default),
2. OAuth credentials missing,
3. the upload itself is not built yet.
It never reports a fake successful upload.
"""

from app.core.config import Settings
from app.core.errors import (
    IntegrationNotConfiguredError,
    IntegrationNotImplementedError,
    PublishingDisabledError,
)
from app.services.youtube.base import UploadRequest, UploadResult


class YouTubeDataAPIPublisher:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def check_ready(self) -> None:
        if not self._settings.youtube_publishing_enabled:
            raise PublishingDisabledError(
                "Publishing is disabled. Set YOUTUBE_PUBLISHING_ENABLED=true only when you are ready to upload."
            )
        if not self._settings.youtube_configured:
            raise IntegrationNotConfiguredError(
                "YouTube is not configured. Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN."
            )

    def upload(self, request: UploadRequest) -> UploadResult:
        self.check_ready()
        raise IntegrationNotImplementedError("YouTube upload is not implemented yet (roadmap Phase 5).")
