from app.core.config import Settings
from app.services.ai.base import AIProvider


def get_ai_provider(settings: Settings) -> AIProvider:
    """Return the configured provider (AI_PROVIDER). Raises a clear error if its key is missing."""
    if settings.ai_provider == "claude":
        from app.services.ai.claude import ClaudeProvider

        return ClaudeProvider(settings)
    from app.services.ai.gemini import GeminiProvider

    return GeminiProvider(settings)
