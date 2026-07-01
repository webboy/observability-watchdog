"""Database model metadata tests."""

from app.models import App, Base, IngestionRun, LogEvent


def test_core_models_are_registered() -> None:
    """Core Phase 1 models should be registered on metadata."""
    table_names = Base.metadata.tables.keys()
    assert "apps" in table_names
    assert "ingestion_runs" in table_names
    assert "log_events" in table_names


def test_app_model_table_name() -> None:
    """App model should map to apps table."""
    assert App.__tablename__ == "apps"


def test_ingestion_run_model_table_name() -> None:
    """IngestionRun model should map to ingestion_runs table."""
    assert IngestionRun.__tablename__ == "ingestion_runs"


def test_log_event_model_has_dedupe_index() -> None:
    """LogEvent should define dedupe unique index."""
    index_names = {index.name for index in LogEvent.__table__.indexes}
    assert "uq_log_events_app_dedupe" in index_names
