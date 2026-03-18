"""Add YuniKorn queue fields to environments.

Revision ID: 20260317_000004
Revises: 20260317_000003
Create Date: 2026-03-17 00:00:04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260317_000004"
down_revision: Union[str, None] = "20260317_000003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("environments")}

    if "yunikorn_queue" not in columns:
        op.add_column(
            "environments",
            sa.Column("yunikorn_queue", sa.String(255), nullable=True),
        )
    if "yunikorn_queue_guaranteed_vcpu" not in columns:
        op.add_column(
            "environments",
            sa.Column("yunikorn_queue_guaranteed_vcpu", sa.Integer, nullable=True),
        )
    if "yunikorn_queue_max_vcpu" not in columns:
        op.add_column(
            "environments",
            sa.Column("yunikorn_queue_max_vcpu", sa.Integer, nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("environments")}

    for col in ("yunikorn_queue_max_vcpu", "yunikorn_queue_guaranteed_vcpu", "yunikorn_queue"):
        if col in columns:
            op.drop_column("environments", col)
