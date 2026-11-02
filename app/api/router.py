from fastapi import APIRouter, Depends

from app.api.deps import require_api_key
from app.api.routes import (
    analytics,
    channels,
    dashboard,
    insights,
    metadata,
    projects,
    publishing,
    renders,
    reports,
    scripts,
    system,
)

api_router = APIRouter(dependencies=[Depends(require_api_key)])
for module in (
    system,
    channels,
    projects,
    scripts,
    renders,
    metadata,
    publishing,
    analytics,
    insights,
    reports,
    dashboard,
):
    api_router.include_router(module.router)
