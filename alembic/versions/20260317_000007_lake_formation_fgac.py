"""Add Lake Formation FGAC fields.

Revision ID: 20260317_000007
Revises: 20260317_000006
Create Date: 2026-03-17 00:00:07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260317_000007"
down_revision: Union[str, None] = "20260317_000006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Environment FGAC columns
    env_columns = {column["name"] for column in inspector.get_columns("environments")}
    if "lake_formation_enabled" not in env_columns:
        op.add_column(
            "environments",
            sa.Column("lake_formation_enabled", sa.Boolean(), nullable=False, server_default="0"),
        )
    if "lf_catalog_id" not in env_columns:
        op.add_column(
            "environments",
            sa.Column("lf_catalog_id", sa.String(255), nullable=True),
        )
    if "lf_data_access_scope_json" not in env_columns:
        op.add_column(
            "environments",
            sa.Column("lf_data_access_scope_json", sa.JSON(), nullable=True),
        )

    # Golden path data access scope
    gp_columns = {column["name"] for column in inspector.get_columns("golden_paths")}
    if "data_access_scope_json" not in gp_columns:
        op.add_column(
            "golden_paths",
            sa.Column("data_access_scope_json", sa.JSON(), nullable=True),
        )

    # EKS identity mode (#52)
    if "identity_mode" not in env_columns:
        op.add_column(
            "environments",
            sa.Column("identity_mode", sa.String(32), nullable=True),
        )

    # EMR Security Configuration (#53)
    if "security_configuration_id" not in env_columns:
        op.add_column(
            "environments",
            sa.Column("security_configuration_id", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("environments", "security_configuration_id")
    op.drop_column("environments", "identity_mode")
    op.drop_column("golden_paths", "data_access_scope_json")
    op.drop_column("environments", "lf_data_access_scope_json")
    op.drop_column("environments", "lf_catalog_id")
    op.drop_column("environments", "lake_formation_enabled")
