"""Add job_templates table and job_template_id on runs.

Revision ID: 20260317_000002
Revises: 20260311_000002
Create Date: 2026-03-17 00:00:02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260317_000002"
down_revision: Union[str, None] = "20260311_000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "job_templates" not in existing_tables:
        op.create_table(
            "job_templates",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("environment_id", sa.String(36), sa.ForeignKey("environments.id"), nullable=False),
            sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=False, server_default=""),
            sa.Column("emr_template_id", sa.String(255), nullable=True),
            sa.Column("job_driver_json", sa.JSON, nullable=False),
            sa.Column("configuration_overrides_json", sa.JSON, nullable=False),
            sa.Column("tags_json", sa.JSON, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("environment_id", "name", name="uq_job_templates_env_name"),
        )

    runs_columns = {col["name"] for col in inspector.get_columns("runs")}
    if "job_template_id" not in runs_columns:
        op.add_column(
            "runs",
            sa.Column("job_template_id", sa.String(36), sa.ForeignKey("job_templates.id"), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    runs_columns = {col["name"] for col in inspector.get_columns("runs")}
    if "job_template_id" in runs_columns:
        op.drop_column("runs", "job_template_id")
    existing_tables = inspector.get_table_names()
    if "job_templates" in existing_tables:
        op.drop_table("job_templates")
