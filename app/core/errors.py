"""Domain errors, mapped to HTTP responses in `app.main`."""


class AutopilotError(Exception):
    """Base class for expected, user-facing errors."""

    status_code = 400
    code = "autopilot_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AutopilotError):
    status_code = 404
    code = "not_found"


class ConflictError(AutopilotError):
    status_code = 409
    code = "conflict"


class InvalidStateTransitionError(ConflictError):
    code = "invalid_state_transition"


class IntegrationNotConfiguredError(AutopilotError):
    """An external service is needed but its credentials are missing."""

    status_code = 503
    code = "integration_not_configured"


class IntegrationNotImplementedError(AutopilotError):
    """The interface exists but the real integration is a later roadmap phase."""

    status_code = 501
    code = "integration_not_implemented"


class PublishingDisabledError(AutopilotError):
    status_code = 403
    code = "publishing_disabled"


class ProviderError(AutopilotError):
    """An external provider call failed or returned unusable output."""

    status_code = 502
    code = "provider_error"


class RenderError(AutopilotError):
    status_code = 500
    code = "render_error"
