"""merge heads: join emr/databricks/lake-formation branch with job-templates/spark-history branch

Revision ID: 20260401_000010
Revises: 20260317_000005, 20260331_000008
Create Date: 2026-04-01

"""

from alembic import op
import sqlalchemy as sa
from typing import Union

# revision identifiers, used by Alembic.
revision: str = "20260401_000010"
down_revision: Union[str, tuple] = ("20260317_000005", "20260331_000008")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
