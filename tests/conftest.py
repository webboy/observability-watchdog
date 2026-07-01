"""Shared pytest fixtures."""

from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.main import app
from app.seeds.anomaly_rules import seed_default_anomaly_rules


def _resolve_test_database_url() -> str:
    return os.getenv("TEST_DATABASE_URL", get_settings().test_database_url)


def _validate_test_database_url(database_url: str) -> None:
    """Refuse to truncate non-test databases unless explicitly overridden."""
    if os.getenv("ALLOW_DEV_DB_TESTS") == "1" or get_settings().allow_dev_db_tests:
        return

    db_name = urlparse(database_url).path.lstrip("/").split("?")[0]
    if "test" not in db_name.lower():
        raise RuntimeError(
            "Refusing to run tests against a non-test database. "
            f"Resolved database name: '{db_name}'. "
            "Use TEST_DATABASE_URL with a test database name or set ALLOW_DEV_DB_TESTS=1."
        )


@pytest.fixture(scope="session", autouse=True)
def configure_test_database() -> None:
    """Bind SQLAlchemy to the dedicated test database for the whole session."""
    import app.database as database_module

    test_database_url = _resolve_test_database_url()
    _validate_test_database_url(test_database_url)

    test_engine = create_engine(test_database_url, pool_pre_ping=True)
    database_module.engine.dispose()
    database_module.engine = test_engine
    database_module.SessionLocal.configure(bind=test_engine)

    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def ensure_anomaly_rules(db_session: Session) -> None:
    """Ensure global anomaly rules exist for detection tests."""
    seed_default_anomaly_rules(db_session)


@pytest.fixture
def db_session() -> Session:
    """Provide a database session and clean core tables between tests."""
    from app.database import SessionLocal

    session = SessionLocal()
    session.execute(
        text(
            "TRUNCATE TABLE alerts, anomalies, metric_windows, log_events, ingestion_runs, apps "
            "RESTART IDENTITY CASCADE"
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """Provide a FastAPI test client bound to the test database session."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
