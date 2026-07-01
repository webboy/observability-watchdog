"""Dedupe service unit tests."""

import hashlib
import io
import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.services.dedupe_service import generate_dedupe_key
from app.services.ecs_parser import ParsedLogEvent


def _sample_event(**overrides) -> ParsedLogEvent:
    defaults = {
        "timestamp": datetime(2026, 6, 30, 12, 1, tzinfo=timezone.utc),
        "service_name": "payment-service",
        "log_level": "ERROR",
        "message": "Payment timeout",
        "raw_event_json": {"message": "Payment timeout"},
        "url_path": "/payments/charge",
        "http_status_code": 502,
        "error_type": "UpstreamTimeout",
    }
    defaults.update(overrides)
    return ParsedLogEvent(**defaults)


def test_dedupe_key_stable_for_same_event() -> None:
    """Same normalized event should produce the same dedupe key."""
    app_id = uuid.uuid4()
    parsed = _sample_event()

    first = generate_dedupe_key(app_id, parsed)
    second = generate_dedupe_key(app_id, parsed)

    assert first == second
    assert len(first) == 64


def test_different_messages_do_not_collide() -> None:
    """Events with same timestamp/service but different messages should differ."""
    app_id = uuid.uuid4()
    first = generate_dedupe_key(app_id, _sample_event(message="Payment timeout"))
    second = generate_dedupe_key(app_id, _sample_event(message="Checkout failed"))

    assert first != second


def test_event_id_path_is_app_scoped() -> None:
    """event.id dedupe keys should include app boundary."""
    parsed = _sample_event(event_id="evt-123")
    app_a = uuid.uuid4()
    app_b = uuid.uuid4()

    assert generate_dedupe_key(app_a, parsed) != generate_dedupe_key(app_b, parsed)


def test_event_id_dedupe_differs_from_sha256_fallback() -> None:
    """event.id path should differ from the SHA-256 fallback for the same payload."""
    app_id = uuid.uuid4()
    parsed = _sample_event(event_id="evt-123")

    event_id_key = generate_dedupe_key(app_id, parsed)
    fallback_key = generate_dedupe_key(app_id, _sample_event(event_id=None))

    assert event_id_key != fallback_key
    expected = hashlib.sha256(f"event_id:{app_id}:evt-123".encode("utf-8")).hexdigest()
    assert event_id_key == expected


def test_event_id_dedupe_ignores_message_changes() -> None:
    """event.id identity should remain stable when message content changes."""
    app_id = uuid.uuid4()
    first = generate_dedupe_key(app_id, _sample_event(event_id="evt-123", message="First"))
    second = generate_dedupe_key(app_id, _sample_event(event_id="evt-123", message="Second"))

    assert first == second


@pytest.mark.parametrize(
    ("field_name", "first_value", "second_value"),
    [
        ("service_name", "payment-service", "checkout-service"),
        ("log_level", "ERROR", "WARN"),
        ("url_path", "/payments/charge", "/checkout/cart"),
        ("http_status_code", 502, 503),
        ("error_type", "UpstreamTimeout", "GatewayError"),
    ],
)
def test_fallback_sha256_includes_canonical_fields(
    field_name: str,
    first_value,
    second_value,
) -> None:
    """Fallback dedupe should change when canonical identity fields change."""
    app_id = uuid.uuid4()
    first = generate_dedupe_key(app_id, _sample_event(event_id=None, **{field_name: first_value}))
    second = generate_dedupe_key(app_id, _sample_event(event_id=None, **{field_name: second_value}))

    assert first != second


def test_duplicate_file_upload_skips_repeated_jsonl_lines(client: TestClient) -> None:
    """Repeated JSONL lines in one upload should accept one and skip one duplicate."""
    response = client.post(
        "/api/v1/apps",
        json={
            "name": "Dedupe Upload",
            "slug": f"dedupe-upload-{uuid.uuid4().hex[:8]}",
            "environment": "production",
        },
    )
    assert response.status_code == 201
    app_id = response.json()["id"]

    line = json.dumps(
        {
            "@timestamp": "2026-06-30T12:01:00Z",
            "log.level": "ERROR",
            "message": "Payment timeout",
            "service.name": "payment-service",
        }
    )
    content = f"{line}\n{line}\n"

    upload_response = client.post(
        f"/api/v1/apps/{app_id}/logs/upload",
        files={"file": ("duplicate.jsonl", io.BytesIO(content.encode("utf-8")), "application/jsonl")},
    )

    assert upload_response.status_code == 201
    payload = upload_response.json()
    assert payload["accepted_events"] == 1
    assert payload["skipped_duplicates"] == 1
