"""analytics snapshot engaged views (viewers who stayed past the first seconds)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-07 21:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("analytics_snapshots") as batch:
        batch.add_column(sa.Column("engaged_views", sa.BigInteger()))


def downgrade() -> None:
    with op.batch_alter_table("analytics_snapshots") as batch:
        batch.drop_column("engaged_views")
