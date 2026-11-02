"""Application settings.

Every secret and environment-specific value is read from environment variables
(or a local `.env` file in development). Nothing sensitive is hardcoded.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]
ClaudeEffort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Application -------------------------------------------------------
    app_name: str = "YouTube-Autopilot"
    environment: Environment = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=list)

    # Optional shared-secret auth for the dashboard API (sent as X-API-Key).
    # Required when ENVIRONMENT=production.
    api_key: SecretStr | None = None

    # --- Database (PostgreSQL / Supabase) ---------------------------------
    # Example: postgresql+psycopg://user:password@host:5432/postgres
    # SQLite is accepted for local development and tests only.
    database_url: str = "sqlite:///./autopilot.db"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 5

    # --- AI provider: Claude (Anthropic) ----------------------------------
    anthropic_api_key: SecretStr | None = None
    claude_model: str = "claude-opus-5-5"
    claude_effort: ClaudeEffort = "medium"
    claude_max_tokens: int = 16000
    # Server-side refusal fallbacks (Anthropic beta). Disable if your account
    # or platform does not support it.
    claude_server_fallbacks: bool = True
    claude_timeout_seconds: float = 600.0

    # --- YouTube (Data API v3 + Analytics API) ----------------------------
    youtube_client_id: SecretStr | None = None
    youtube_client_secret: SecretStr | None = None
    youtube_refresh_token: SecretStr | None = None
    # Hard safety switch. Uploads are refused while this is false.
    youtube_publishing_enabled: bool = False

    # --- Video rendering --------------------------------------------------
    blender_binary: str = "blender"
    blender_timeout_seconds: int = 4 * 3600
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    media_root: Path = Path("./media")
    # YouTube currently accepts vertical Shorts up to 3 minutes.
    shorts_max_duration_seconds: int = 180
    long_form_min_duration_seconds: int = 181

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        if self.environment == "production":
            if self.database_url.startswith("sqlite"):
                raise ValueError("DATABASE_URL must point to PostgreSQL in production.")
            if self.api_key is None:
                raise ValueError("API_KEY must be set in production.")
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def claude_configured(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value())

    @property
    def youtube_configured(self) -> bool:
        values = (self.youtube_client_id, self.youtube_client_secret, self.youtube_refresh_token)
        return all(v is not None and v.get_secret_value() for v in values)


@lru_cache
def get_settings() -> Settings:
    return Settings()
