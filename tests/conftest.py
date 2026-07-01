"""Shared pytest fixtures."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.main import app
from app.seeds.anomaly_rules import seed_default_anomaly_rules


@pytest.fixture(autouse=True)
def ensure_anomaly_rules(db_session: Session) -> None:
    """Ensure global anomaly rules exist for detection tests."""
    seed_default_anomaly_rules(db_session)


@pytest.fixture
def db_session() -> Session:
    """Provide a database session and clean core tables between tests."""
    session = SessionLocal()
    session.execute(
        text(
            "TRUNCATE TABLE anomalies, metric_windows, log_events, ingestion_runs, apps "
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
