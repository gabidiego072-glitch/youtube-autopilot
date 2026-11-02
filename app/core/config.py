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

    # --- Research (free) ----------------------------------------------------
    research_enabled: bool = True
    wikipedia_language: str = "es"
    # Wikimedia asks for a descriptive agent with contact info.
    wikipedia_user_agent: str = "YouTubeAutopilot/0.2 (set WIKIPEDIA_USER_AGENT with your contact)"

    # --- AI images / video ------------------------------------------------
    # Option A (free, self-hosted): ComfyUI running open models (e.g. FLUX.1-schnell, Wan 2.x).
    comfyui_url: str | None = None
    comfyui_image_workflow: Path | None = None  # API-format workflow JSON with {{placeholders}}
    comfyui_video_workflow: Path | None = None
    # Option B (free tier): Hugging Face Inference Providers.
    hf_token: SecretStr | None = None
    hf_image_model: str = "black-forest-labs/FLUX.1-schnell"
    hf_inference_url: str = "https://router.huggingface.co/hf-inference/models"
    visuals_timeout_seconds: float = 300.0

    # --- Voice (free, local) ----------------------------------------------
    piper_binary: str = "piper"
    piper_voice_model: Path | None = None
    piper_length_scale: float = 0.92  # <1 = faster, livelier narration

    # --- Video rendering --------------------------------------------------
    blender_binary: str = "blender"
    blender_timeout_seconds: int = 4 * 3600
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    media_root: Path = Path("./media")
    # YouTube currently accepts vertical Shorts up to 3 minutes.
    # Final edit resolution as a fraction of 1080p (e.g. 0.5 for fast previews).
    edit_resolution_scale: float = 1.0
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
    def image_provider_name(self) -> str | None:
        if self.comfyui_url and self.comfyui_image_workflow:
            return "comfyui"
        if self.hf_token and self.hf_token.get_secret_value():
            return "huggingface"
        return None

    @property
    def youtube_configured(self) -> bool:
        values = (self.youtube_client_id, self.youtube_client_secret, self.youtube_refresh_token)
        return all(v is not None and v.get_secret_value() for v in values)


@lru_cache
def get_settings() -> Settings:
    return Settings()
