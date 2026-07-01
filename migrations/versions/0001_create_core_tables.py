"""Create core tables: apps, ingestion_runs, log_events."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_create_core_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create apps, ingestion_runs, and log_events tables."""
    op.create_table(
        "apps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "environment",
            sa.String(length=100),
            server_default="production",
            nullable=False,
        ),
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
    op.create_index("ix_apps_slug", "apps", ["slug"], unique=True)

    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("total_lines", sa.Integer(), server_default="0", nullable=False),
        sa.Column("accepted_events", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_events", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_duplicates", sa.Integer(), server_default="0", nullable=False),
        sa.Column("detected_anomalies", sa.Integer(), server_default="0", nullable=False),
        sa.Column("alerts_triggered", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default="processing",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_runs_app_id", "ingestion_runs", ["app_id"], unique=False)
    op.create_index("ix_ingestion_runs_status", "ingestion_runs", ["status"], unique=False)
    op.create_index(
        "idx_ingestion_runs_app_created",
        "ingestion_runs",
        ["app_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "log_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=True),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("service_name", sa.String(length=255), nullable=False),
        sa.Column("log_level", sa.String(length=50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("event_dataset", sa.String(length=255), nullable=True),
        sa.Column("event_outcome", sa.String(length=100), nullable=True),
        sa.Column("event_duration_ns", sa.BigInteger(), nullable=True),
        sa.Column("http_status_code", sa.Integer(), nullable=True),
        sa.Column("url_path", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=255), nullable=True),
        sa.Column("span_id", sa.String(length=255), nullable=True),
        sa.Column("transaction_id", sa.String(length=255), nullable=True),
        sa.Column("error_type", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_event_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingestion_run_id"], ["ingestion_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_log_events_app_dedupe",
        "log_events",
        ["app_id", "dedupe_key"],
        unique=True,
    )
    op.create_index(
        "idx_log_events_app_timestamp",
        "log_events",
        ["app_id", "timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_log_events_app_service_timestamp",
        "log_events",
        ["app_id", "service_name", "timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_log_events_app_level_timestamp",
        "log_events",
        ["app_id", "log_level", "timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_log_events_raw_json",
        "log_events",
        ["raw_event_json"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Drop core tables."""
    op.drop_index("idx_log_events_raw_json", table_name="log_events", postgresql_using="gin")
    op.drop_index("idx_log_events_app_level_timestamp", table_name="log_events")
    op.drop_index("idx_log_events_app_service_timestamp", table_name="log_events")
    op.drop_index("idx_log_events_app_timestamp", table_name="log_events")
    op.drop_index("uq_log_events_app_dedupe", table_name="log_events")
    op.drop_table("log_events")

    op.drop_index("idx_ingestion_runs_app_created", table_name="ingestion_runs")
    op.drop_index("ix_ingestion_runs_status", table_name="ingestion_runs")
    op.drop_index("ix_ingestion_runs_app_id", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")

    op.drop_index("ix_apps_slug", table_name="apps")
    op.drop_table("apps")
