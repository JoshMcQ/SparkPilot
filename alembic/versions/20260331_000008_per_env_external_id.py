"""Add per-environment assume_role_external_id field.

Revision ID: 20260331_000008
Revises: 20260317_000007
Create Date: 2026-03-31 00:00:08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260331_000008"
down_revision: Union[str, None] = "20260317_000007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    op.drop_column("environments", "assume_role_external_id")
