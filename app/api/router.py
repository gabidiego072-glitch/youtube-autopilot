from fastapi import APIRouter, Depends

from app.api.deps import require_api_key
from app.api.routes import (
    analytics,
    channels,
    dashboard,
    ideas,
    insights,
    media,
    metadata,
    projects,
    publishing,
    renders,
    reports,
    research,
    scripts,
    system,
)

api_router = APIRouter(dependencies=[Depends(require_api_key)])
for module in (
    system,
    channels,
    ideas,
    projects,
    research,
    scripts,
    media,
    renders,
    metadata,
    publishing,
    analytics,
    insights,
    reports,
    dashboard,
):
    api_router.include_router(module.router)
