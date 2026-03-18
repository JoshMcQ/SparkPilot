"""Add Databricks workspace fields to environments.

Revision ID: 20260317_000006
Revises: 20260317_000001
Create Date: 2026-03-17 00:00:06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260317_000006"
down_revision: Union[str, None] = "20260317_000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    env_columns = {column["name"] for column in inspector.get_columns("environments")}
    if "databricks_workspace_url" not in env_columns:
        op.add_column(
            "environments",
            sa.Column("databricks_workspace_url", sa.String(2048), nullable=True),
        )
    if "databricks_cluster_policy_id" not in env_columns:
        op.add_column(
            "environments",
            sa.Column("databricks_cluster_policy_id", sa.String(255), nullable=True),
        )
    if "databricks_instance_pool_id" not in env_columns:
        op.add_column(
            "environments",
            sa.Column("databricks_instance_pool_id", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    env_columns = {column["name"] for column in inspector.get_columns("environments")}
    if "databricks_workspace_url" in env_columns:
        op.drop_column("environments", "databricks_workspace_url")
    if "databricks_cluster_policy_id" in env_columns:
        op.drop_column("environments", "databricks_cluster_policy_id")
    if "databricks_instance_pool_id" in env_columns:
        op.drop_column("environments", "databricks_instance_pool_id")
