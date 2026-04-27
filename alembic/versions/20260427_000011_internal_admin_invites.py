"""Add internal-admin users and magic-link invite tables.

Revision ID: 20260427_000011
Revises: 20260401_000010
Create Date: 2026-04-27 00:00:11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260427_000011"
down_revision: Union[str, None] = "20260401_000010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "tenants"):
        tenant_columns = _column_names(inspector, "tenants")
        if "federation_type" not in tenant_columns:
            op.add_column(
                "tenants",
                sa.Column(
                    "federation_type",
                    sa.String(length=32),
                    nullable=False,
                    server_default="cognito_password",
                ),
            )
        if "idp_metadata_json" not in tenant_columns:
            op.add_column(
                "tenants",
                sa.Column("idp_metadata_json", sa.JSON(), nullable=True),
            )

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column(
                "role",
                sa.String(length=32),
                nullable=False,
                server_default="admin",
            ),
            sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("invite_consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("role IN ('admin','member')", name="ck_users_role"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        )
    else:
        user_columns = _column_names(inspector, "users")
        if "invited_at" not in user_columns:
            op.add_column(
                "users",
                sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
            )
        if "invite_consumed_at" not in user_columns:
            op.add_column(
                "users",
                sa.Column(
                    "invite_consumed_at", sa.DateTime(timezone=True), nullable=True
                ),
            )

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "user_identities"):
        identity_columns = _column_names(inspector, "user_identities")
        if "user_id" not in identity_columns:
            with op.batch_alter_table("user_identities") as batch_op:
                batch_op.add_column(
                    sa.Column("user_id", sa.String(length=36), nullable=True)
                )
                batch_op.create_foreign_key(
                    "fk_user_identities_user_id_users",
                    "users",
                    ["user_id"],
                    ["id"],
                )

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "magic_link_tokens"):
        op.create_table(
            "magic_link_tokens",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("purpose", sa.String(length=32), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by", sa.String(length=255), nullable=False),
            sa.CheckConstraint(
                "purpose IN ('invite_accept')",
                name="ck_magic_link_tokens_purpose",
            ),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash", name="uq_magic_link_tokens_token_hash"),
        )
        op.create_index(
            "ix_magic_link_tokens_user_purpose",
            "magic_link_tokens",
            ["user_id", "purpose"],
        )

    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "magic_link_logs"):
        op.create_table(
            "magic_link_logs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column(
                "purpose",
                sa.String(length=32),
                nullable=False,
                server_default="invite_accept",
            ),
            sa.Column("magic_link_url", sa.Text(), nullable=False),
            sa.Column("created_by", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_magic_link_logs_user_created",
            "magic_link_logs",
            ["user_id", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "magic_link_logs"):
        op.drop_table("magic_link_logs")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "magic_link_tokens"):
        op.drop_table("magic_link_tokens")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "user_identities"):
        identity_columns = _column_names(inspector, "user_identities")
        if "user_id" in identity_columns:
            with op.batch_alter_table("user_identities") as batch_op:
                batch_op.drop_column("user_id")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "users"):
        op.drop_table("users")

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "tenants"):
        tenant_columns = _column_names(inspector, "tenants")
        if "idp_metadata_json" in tenant_columns:
            op.drop_column("tenants", "idp_metadata_json")
        if "federation_type" in tenant_columns:
            op.drop_column("tenants", "federation_type")
