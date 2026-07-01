"""Add incident summary metadata columns to anomalies."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_incident_metadata"
down_revision: Union[str, None] = "0003_add_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add business_impact and generation_source to anomalies."""
    op.add_column("anomalies", sa.Column("business_impact", sa.Text(), nullable=True))
    op.add_column("anomalies", sa.Column("generation_source", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Remove incident summary metadata columns from anomalies."""
    op.drop_column("anomalies", "generation_source")
    op.drop_column("anomalies", "business_impact")
