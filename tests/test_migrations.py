"""Migrations must build the same schema as the models, on SQLite and (optionally) PostgreSQL.

Set TEST_POSTGRES_URL (e.g. postgresql+psycopg://user:pass@localhost/db) to also
run against a real PostgreSQL database. That database is wiped by the test.
"""

import os

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from alembic import command
from app.models import Base


def _alembic_config(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _assert_round_trip(url: str) -> None:
    cfg = _alembic_config(url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
        tables = set(inspect(conn).get_table_names())
    assert diff == [], diff
    assert set(Base.metadata.tables) <= tables
    command.downgrade(cfg, "base")
    with engine.connect() as conn:
        assert set(inspect(conn).get_table_names()) <= {"alembic_version"}
    engine.dispose()


def test_migrations_sqlite(tmp_path):
    _assert_round_trip(f"sqlite:///{tmp_path / 'm.db'}")


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not set")
def test_migrations_postgres():
    _assert_round_trip(os.environ["TEST_POSTGRES_URL"])
