"""Add per-environment assume_role_external_id field.

Revision ID: 20260331_000008
Revises: 20260317_000007
Create Date: 2026-03-31 00:00:08
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260331_000008"
down_revision: str | None = "20260317_000007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    env_columns = {column["name"] for column in inspector.get_columns("environments")}

    if "assume_role_external_id" not in env_columns:
        op.add_column(
            "environments",
            sa.Column("assume_role_external_id", sa.String(1024), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "assume_role_external_id" in {col["name"] for col in inspector.get_columns("environments")}:
        op.drop_column("environments", "assume_role_external_id")
