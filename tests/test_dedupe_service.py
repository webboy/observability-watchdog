"""Dedupe service unit tests."""

import uuid
from datetime import datetime, timezone

from app.services.dedupe_service import generate_dedupe_key
from app.services.ecs_parser import ParsedLogEvent


def _sample_event(**overrides) -> ParsedLogEvent:
    defaults = {
        "timestamp": datetime(2026, 6, 30, 12, 1, tzinfo=timezone.utc),
        "service_name": "payment-service",
        "log_level": "ERROR",
        "message": "Payment timeout",
        "raw_event_json": {"message": "Payment timeout"},
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
