"""Add run last_heartbeat_at column for long-running lifecycle health.

Revision ID: 20260311_000002
Revises: 20260305_000001
Create Date: 2026-03-11 00:00:02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260311_000002"
down_revision: Union[str, None] = "20260305_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("runs")}
    if "last_heartbeat_at" not in columns:
        op.add_column("runs", sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("runs")}
    if "last_heartbeat_at" in columns:
        op.drop_column("runs", "last_heartbeat_at")
