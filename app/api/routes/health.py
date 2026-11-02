from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.api.deps import DbSession, SettingsDep

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: SettingsDep) -> dict:
    """Liveness probe. Does not touch the database."""
    return {"status": "ok", "version": __version__, "environment": settings.environment}


@router.get("/health/ready")
def readiness(db: DbSession) -> dict:
    """Readiness probe. Verifies the database connection."""
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}
