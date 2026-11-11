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

    # --- AI provider ---------------------------------------------------------
    # gemini: free tier of Google AI Studio (default). claude: paid, optional.
    ai_provider: Literal["gemini", "claude"] = "gemini"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    # Comma-separated models to try when GEMINI_MODEL is overloaded or out of free quota.
    # Empty = pick other free "flash" models automatically from the models your key can use.
    gemini_fallback_models: str = ""
    gemini_max_tokens: int = 32000
    planned_topics_enabled: bool = True  # app/content/planned_topics.json goes before generated ideas
    # Every video is a first-person journey ("pov") built from hand-made scene recipes, the way the best
    # videos were made by hand; "classic" + recipes off = the older third-person, AI-placed storyboard.
    default_style: str = "pov"
    recipes_enabled: bool = True
    scene_check_enabled: bool = True  # look at every scene before the render: does it show what the voice says?
    gemini_timeout_seconds: float = 300.0

    # --- AI provider: Claude (Anthropic), optional and paid -----------------
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
    # Second switch, only for PUBLIC (or scheduled) videos. While false every upload is private,
    # which is what you want for test uploads and while the API project is not audited.
    youtube_allow_public: bool = False
    youtube_default_privacy: Literal["private", "unlisted", "public"] = "private"
    # Post the metadata's "pinned comment" after uploading (needs the youtube.force-ssl scope;
    # pinning itself is only possible by hand in YouTube Studio).
    youtube_post_comment: bool = False
    # Optional API key (no OAuth) for public data: trends and competitor research.
    youtube_api_key: SecretStr | None = None
    youtube_region_code: str = "ES"
    youtube_upload_chunk_mb: int = 8

    # --- Research (free) ----------------------------------------------------
    research_enabled: bool = True
    # Trend signals for new ideas: Wikipedia pageviews (free) + YouTube search if YOUTUBE_API_KEY is set.
    trends_enabled: bool = True
    wikipedia_language: str = "es"
    # Wikimedia asks for a descriptive agent with contact info.
    wikipedia_user_agent: str = "YouTubeAutopilot/0.3 (+https://github.com/gabidiego072-glitch/youtube-autopilot)"

    # --- Procedural 3D scenes (Blender) ----------------------------------
    scene_render_quality: str = "draft"  # test | draft | preview | final
    scene_render_threads: int = 0  # 0 = all cores

    # --- Voice (free, local) ----------------------------------------------
    piper_binary: str = "piper"
    piper_voice_model: Path | None = None
    piper_length_scale: float = 0.92  # <1 = faster, livelier narration
    # Kokoro-82M (natural voices, Apache-2.0): model folder from scripts/install_kokoro.sh.
    kokoro_model_dir: Path | None = Path("models/kokoro")
    kokoro_speed: float = 1.05

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
    def _empty_means_default(self) -> "Settings":
        # CI passes unset repository variables as empty strings; an empty User-Agent gets 403 from Wikimedia.
        if not self.wikipedia_user_agent.strip():
            self.wikipedia_user_agent = type(self).model_fields["wikipedia_user_agent"].default
        return self

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
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.get_secret_value())

    @property
    def ai_configured(self) -> bool:
        return self.gemini_configured if self.ai_provider == "gemini" else self.claude_configured

    @property
    def claude_configured(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value())

    @property
    def youtube_api_key_configured(self) -> bool:
        return bool(self.youtube_api_key and self.youtube_api_key.get_secret_value())

    @property
    def youtube_configured(self) -> bool:
        values = (self.youtube_client_id, self.youtube_client_secret, self.youtube_refresh_token)
        return all(v is not None and v.get_secret_value() for v in values)


@lru_cache
def get_settings() -> Settings:
    return Settings()
