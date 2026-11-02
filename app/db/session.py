from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


def build_engine(database_url: str, echo: bool = False, **pool_kwargs) -> Engine:
    if database_url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in database_url or database_url in ("sqlite://", "sqlite:///"):
            kwargs["poolclass"] = StaticPool
        engine = create_engine(database_url, echo=echo, **kwargs)

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):  # pragma: no cover - trivial
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    # pool_pre_ping survives Supabase/pgbouncer dropping idle connections.
    return create_engine(database_url, echo=echo, pool_pre_ping=True, **pool_kwargs)


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    pool_kwargs = {}
    if not settings.is_sqlite:
        pool_kwargs = {
            "pool_size": settings.database_pool_size,
            "max_overflow": settings.database_max_overflow,
        }
    return build_engine(settings.database_url, settings.database_echo, **pool_kwargs)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
