"""Add EMR Serverless and EMR on EC2 engine fields to environments and runs.

Revision ID: 20260317_000001
Revises: 20260311_000002
Create Date: 2026-03-17 00:00:01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260317_000001"
down_revision: Union[str, None] = "20260311_000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    env_columns = {column["name"] for column in inspector.get_columns("environments")}
    if "emr_serverless_application_id" not in env_columns:
        op.add_column(
            "environments",
            sa.Column("emr_serverless_application_id", sa.String(255), nullable=True),
        )
    if "emr_on_ec2_cluster_id" not in env_columns:
        op.add_column(
            "environments",
            sa.Column("emr_on_ec2_cluster_id", sa.String(255), nullable=True),
        )

    run_columns = {column["name"] for column in inspector.get_columns("runs")}
    if "backend_job_run_id" not in run_columns:
        op.add_column(
            "runs",
            sa.Column("backend_job_run_id", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    env_columns = {column["name"] for column in inspector.get_columns("environments")}
    if "emr_serverless_application_id" in env_columns:
        op.drop_column("environments", "emr_serverless_application_id")
    if "emr_on_ec2_cluster_id" in env_columns:
        op.drop_column("environments", "emr_on_ec2_cluster_id")

    run_columns = {column["name"] for column in inspector.get_columns("runs")}
    if "backend_job_run_id" in run_columns:
        op.drop_column("runs", "backend_job_run_id")
