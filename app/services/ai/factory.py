from app.core.config import Settings
from app.services.ai.base import AIProvider
from app.services.ai.claude import ClaudeProvider


def get_ai_provider(settings: Settings) -> AIProvider:
    """Return the configured provider. Raises if credentials are missing."""
    return ClaudeProvider(settings)
