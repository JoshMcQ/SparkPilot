"""Add spark_history_server_url and event_log_s3_uri to environments.

Revision ID: 20260317_000003
Revises: 20260317_000002
Create Date: 2026-03-17 00:00:03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260317_000003"
down_revision: Union[str, None] = "20260317_000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("environments")}

    if "spark_history_server_url" not in columns:
        op.add_column(
            "environments",
            sa.Column("spark_history_server_url", sa.String(2048), nullable=True),
        )
    if "event_log_s3_uri" not in columns:
        op.add_column(
            "environments",
            sa.Column("event_log_s3_uri", sa.String(2048), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("environments")}

    if "event_log_s3_uri" in columns:
        op.drop_column("environments", "event_log_s3_uri")
    if "spark_history_server_url" in columns:
        op.drop_column("environments", "spark_history_server_url")
