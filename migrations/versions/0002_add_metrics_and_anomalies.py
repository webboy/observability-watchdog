"""Add metric windows, anomaly rules, and anomalies."""

from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_add_metrics_and_anomalies"
down_revision: Union[str, None] = "0001_create_core_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_RULES = [
    {
        "id": str(uuid.uuid4()),
        "name": "Error count spike",
        "metric_name": "error_count",
        "window_minutes": 10,
        "baseline_window_minutes": 60,
        "warning_multiplier": 3,
        "critical_multiplier": 8,
        "min_event_count": 10,
    },
    {
        "id": str(uuid.uuid4()),
        "name": "HTTP 5xx rate spike",
        "metric_name": "http_5xx_rate",
        "window_minutes": 10,
        "baseline_window_minutes": 60,
        "warning_multiplier": 2,
        "critical_multiplier": 5,
        "min_event_count": 20,
    },
    {
        "id": str(uuid.uuid4()),
        "name": "Latency p95 spike",
        "metric_name": "latency_p95",
        "window_minutes": 10,
        "baseline_window_minutes": 60,
        "warning_multiplier": 2,
        "critical_multiplier": 4,
        "min_event_count": 20,
    },
]


def upgrade() -> None:
    """Create metric/anomaly tables and seed global default rules."""
    op.create_table(
        "anomaly_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("metric_name", sa.String(length=100), nullable=False),
        sa.Column("window_minutes", sa.Integer(), server_default="10", nullable=False),
        sa.Column("baseline_window_minutes", sa.Integer(), server_default="60", nullable=False),
        sa.Column("warning_multiplier", sa.Float(), nullable=False),
        sa.Column("critical_multiplier", sa.Float(), nullable=False),
        sa.Column("min_event_count", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_anomaly_rules_app_id", "anomaly_rules", ["app_id"], unique=False)
    op.create_index("ix_anomaly_rules_metric_name", "anomaly_rules", ["metric_name"], unique=False)

    op.create_table(
        "metric_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_name", sa.String(length=255), nullable=False),
        sa.Column("url_path", sa.Text(), nullable=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_minutes", sa.Integer(), server_default="10", nullable=False),
        sa.Column("total_events", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("error_rate", sa.Float(), nullable=False),
        sa.Column("http_5xx_count", sa.Integer(), nullable=False),
        sa.Column("http_5xx_rate", sa.Float(), nullable=False),
        sa.Column("latency_p95_ms", sa.Float(), nullable=True),
        sa.Column("unique_error_types", sa.Integer(), server_default="0", nullable=False),
        sa.Column("most_common_error_type", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_metric_windows_app_window", "metric_windows", ["app_id", "window_start"])
    op.create_index(
        "idx_metric_windows_app_service_window",
        "metric_windows",
        ["app_id", "service_name", "window_start"],
    )
    op.create_index(
        "uq_metric_windows_scope",
        "metric_windows",
        ["app_id", "service_name", sa.text("COALESCE(url_path, '')"), "window_start", "window_minutes"],
        unique=True,
    )

    op.create_table(
        "anomalies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_name", sa.String(length=255), nullable=False),
        sa.Column("url_path", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("metric_name", sa.String(length=100), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_value", sa.Float(), nullable=False),
        sa.Column("baseline_value", sa.Float(), nullable=False),
        sa.Column("anomaly_score", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("likely_cause", sa.Text(), nullable=True),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["anomaly_rules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_anomalies_app_window", "anomalies", ["app_id", "window_start"])
    op.create_index(
        "uq_anomalies_scope",
        "anomalies",
        [
            "app_id",
            "rule_id",
            "service_name",
            sa.text("COALESCE(url_path, '')"),
            "window_start",
            "metric_name",
        ],
        unique=True,
    )

    rules_table = sa.table(
        "anomaly_rules",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("app_id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String()),
        sa.column("metric_name", sa.String()),
        sa.column("window_minutes", sa.Integer()),
        sa.column("baseline_window_minutes", sa.Integer()),
        sa.column("warning_multiplier", sa.Float()),
        sa.column("critical_multiplier", sa.Float()),
        sa.column("min_event_count", sa.Integer()),
        sa.column("enabled", sa.Boolean()),
    )
    op.bulk_insert(
        rules_table,
        [
            {
                "id": rule["id"],
                "app_id": None,
                "name": rule["name"],
                "metric_name": rule["metric_name"],
                "window_minutes": rule["window_minutes"],
                "baseline_window_minutes": rule["baseline_window_minutes"],
                "warning_multiplier": rule["warning_multiplier"],
                "critical_multiplier": rule["critical_multiplier"],
                "min_event_count": rule["min_event_count"],
                "enabled": True,
            }
            for rule in DEFAULT_RULES
        ],
    )


def downgrade() -> None:
    """Drop metric/anomaly tables."""
    op.drop_index("uq_anomalies_scope", table_name="anomalies")
    op.drop_index("idx_anomalies_app_window", table_name="anomalies")
    op.drop_table("anomalies")

    op.drop_index("uq_metric_windows_scope", table_name="metric_windows")
    op.drop_index("idx_metric_windows_app_service_window", table_name="metric_windows")
    op.drop_index("idx_metric_windows_app_window", table_name="metric_windows")
    op.drop_table("metric_windows")

    op.drop_index("ix_anomaly_rules_metric_name", table_name="anomaly_rules")
    op.drop_index("ix_anomaly_rules_app_id", table_name="anomaly_rules")
    op.drop_table("anomaly_rules")
