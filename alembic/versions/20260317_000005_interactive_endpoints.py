"""Add interactive_endpoints table.

Revision ID: 20260317_000005
Revises: 20260317_000004
Create Date: 2026-03-17 00:00:05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260317_000005"
down_revision: Union[str, None] = "20260317_000004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "interactive_endpoints" not in existing_tables:
        op.create_table(
            "interactive_endpoints",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("environment_id", sa.String(36), sa.ForeignKey("environments.id"), nullable=False),
            sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("emr_endpoint_id", sa.String(255), nullable=True),
            sa.Column("execution_role_arn", sa.String(1024), nullable=False),
            sa.Column("release_label", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="creating"),
            sa.Column("idle_timeout_minutes", sa.Integer, nullable=False, server_default="60"),
            sa.Column("certificate_arn", sa.String(1024), nullable=True),
            sa.Column("endpoint_url", sa.String(2048), nullable=True),
            sa.Column("created_by_actor", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()
    if "interactive_endpoints" in existing_tables:
        op.drop_table("interactive_endpoints")
