"""Initial SparkPilot schema.

Revision ID: 20260305_000001
Revises:
Create Date: 2026-03-05 00:00:01
"""

from typing import Sequence, Union

from alembic import op
from sparkpilot.models import Base


# revision identifiers, used by Alembic.
revision: str = "20260305_000001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
