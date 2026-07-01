"""Log ingestion integration tests."""

import io

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ingestion_run import IngestionRun


def _create_app(client: TestClient) -> str:
    response = client.post(
        "/api/v1/apps",
        json={
            "name": "E-commerce Platform",
            "slug": "ecommerce-platform",
            "environment": "production",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _sample_event(**overrides):
    event = {
        "@timestamp": "2026-06-30T12:01:00Z",
        "log.level": "ERROR",
        "message": "Payment timeout",
        "service.name": "payment-service",
    }
    event.update(overrides)
    return event


def test_batch_ingestion_inserts_valid_events(client: TestClient) -> None:
    """Valid batch ingestion should insert events and return counters."""
    app_id = _create_app(client)

    response = client.post(
        f"/api/v1/apps/{app_id}/logs/events",
        json={"events": [_sample_event(), _sample_event(message="Another failure")]},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["accepted_events"] == 2
    assert payload["rejected_events"] == 0
    assert payload["skipped_duplicates"] == 0
    assert payload["status"] == "completed"


def test_duplicate_batch_increments_skipped_duplicates(client: TestClient) -> None:
    """Re-ingesting the same events should skip duplicates."""
    app_id = _create_app(client)
    body = {"events": [_sample_event()]}

    first = client.post(f"/api/v1/apps/{app_id}/logs/events", json=body)
    second = client.post(f"/api/v1/apps/{app_id}/logs/events", json=body)

    assert first.json()["accepted_events"] == 1
    assert second.json()["accepted_events"] == 0
    assert second.json()["skipped_duplicates"] == 1


def test_invalid_events_increment_rejected_events(client: TestClient) -> None:
    """Invalid events should increment rejected_events without failing the request."""
    app_id = _create_app(client)

    response = client.post(
        f"/api/v1/apps/{app_id}/logs/events",
        json={"events": [_sample_event(), {"message": "missing fields"}]},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["accepted_events"] == 1
    assert payload["rejected_events"] == 1


def test_upload_endpoint_parses_jsonl(client: TestClient) -> None:
    """Upload endpoint should parse JSONL line-by-line."""
    app_id = _create_app(client)
    content = "\n".join(
        [
            '{"@timestamp":"2026-06-30T12:00:00Z","log.level":"INFO","message":"ok","service.name":"checkout-service"}',
            '{"@timestamp":"2026-06-30T12:01:00Z","log.level":"ERROR","message":"fail","service.name":"payment-service"}',
        ]
    )

    response = client.post(
        f"/api/v1/apps/{app_id}/logs/upload",
        files={"file": ("sample_logs.jsonl", io.BytesIO(content.encode("utf-8")), "application/jsonl")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["total_lines"] == 2
    assert payload["accepted_events"] == 2


def test_validate_endpoint_does_not_persist(client: TestClient, db_session: Session) -> None:
    """Validate endpoint should report results without creating ingestion runs."""
    app_id = _create_app(client)

    response = client.post(
        f"/api/v1/apps/{app_id}/logs/validate",
        json={"events": [_sample_event(), {"message": "missing fields"}]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid_events"] == 1
    assert payload["rejected_events"] == 1

    run_count = db_session.scalar(select(func.count()).select_from(IngestionRun))
    assert run_count == 0
