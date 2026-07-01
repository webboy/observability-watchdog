"""Add alerts table."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_add_alerts"
down_revision: Union[str, None] = "0002_add_metrics_and_anomalies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create alerts table."""
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anomaly_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column(
            "delivery_status",
            sa.String(length=50),
            server_default="simulated",
            nullable=False,
        ),
        sa.Column("webhook_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["anomaly_id"], ["anomalies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_alerts_app_created", "alerts", ["app_id", "created_at"])
    op.create_index("idx_alerts_app_severity_created", "alerts", ["app_id", "severity", "created_at"])
    op.create_index("uq_alerts_anomaly_id", "alerts", ["anomaly_id"], unique=True)


def downgrade() -> None:
    """Drop alerts table."""
    op.drop_index("uq_alerts_anomaly_id", table_name="alerts")
    op.drop_index("idx_alerts_app_severity_created", table_name="alerts")
    op.drop_index("idx_alerts_app_created", table_name="alerts")
    op.drop_table("alerts")
