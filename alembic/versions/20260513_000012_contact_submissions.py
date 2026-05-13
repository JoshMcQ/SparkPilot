"""Add contact_submissions table for public interest form.

Revision ID: 20260513_000012
Revises: 20260427_000011
Create Date: 2026-05-13 00:00:12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260513_000012"
down_revision: Union[str, None] = "20260427_000011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "contact_submissions"):
        op.create_table(
            "contact_submissions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("company", sa.String(length=255), nullable=True),
            sa.Column("use_case", sa.String(length=255), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("source_ip", sa.String(length=45), nullable=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=True),
            sa.Column("approved_by", sa.String(length=255), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint(
                "status IN ('pending', 'approved', 'rejected')",
                name="ck_contact_submissions_status",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_contact_submissions_status_created",
            "contact_submissions",
            ["status", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "contact_submissions"):
        op.drop_index("ix_contact_submissions_status_created", table_name="contact_submissions")
        op.drop_table("contact_submissions")
