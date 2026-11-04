"""video project features (experiment variants)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-04 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("video_projects") as batch:
        batch.add_column(
            sa.Column("features", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"))
        )


def downgrade() -> None:
    with op.batch_alter_table("video_projects") as batch:
        batch.drop_column("features")
