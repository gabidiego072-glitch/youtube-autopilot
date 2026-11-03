from pydantic import BaseModel


class IntegrationState(BaseModel):
    configured: bool
    implemented: bool
    detail: str


class IntegrationsStatus(BaseModel):
    claude: IntegrationState
    ffmpeg: IntegrationState
    blender: IntegrationState
    voice: IntegrationState
    research: IntegrationState
    youtube_data_api: IntegrationState
    youtube_analytics_api: IntegrationState
    publishing_enabled: bool


class DashboardSummary(BaseModel):
    channels: int
    projects_by_status: dict[str, int]
    projects_by_format: dict[str, int]
    projects_by_category: dict[str, int]
    ideas_by_status: dict[str, int]
    render_jobs_by_status: dict[str, int]
    videos_with_analytics: int
    total_views: int
    latest_insights: list[dict]
    integrations: IntegrationsStatus
