"""ECS parser unit tests."""

from datetime import timezone

import pytest

from app.services.ecs_parser import ParseFailure, parse_event, parse_json_line


def test_parse_event_with_dotted_keys() -> None:
    """Parser should normalize flat dotted ECS keys."""
    result = parse_event(
        {
            "@timestamp": "2026-06-30T12:01:00Z",
            "log.level": "ERROR",
            "message": "Payment timeout",
            "service.name": "payment-service",
            "http.response.status_code": 502,
            "url.path": "/payments/charge",
        }
    )

    assert not isinstance(result, ParseFailure)
    assert result.service_name == "payment-service"
    assert result.http_status_code == 502
    assert result.url_path == "/payments/charge"
    assert result.timestamp.tzinfo == timezone.utc


def test_parse_event_with_nested_keys() -> None:
    """Parser should normalize nested ECS objects."""
    result = parse_event(
        {
            "@timestamp": "2026-06-30T12:01:00Z",
            "log": {"level": "ERROR"},
            "message": "Payment timeout",
            "service": {"name": "payment-service"},
            "http": {"response": {"status_code": 502}},
            "url": {"path": "/payments/charge"},
        }
    )

    assert not isinstance(result, ParseFailure)
    assert result.service_name == "payment-service"
    assert result.http_status_code == 502
    assert result.url_path == "/payments/charge"


def test_dotted_key_preferred_over_nested_with_warning() -> None:
    """Dotted ECS keys should win when both representations exist."""
    result = parse_event(
        {
            "@timestamp": "2026-06-30T12:01:00Z",
            "log.level": "ERROR",
            "log": {"level": "INFO"},
            "message": "Payment timeout",
            "service.name": "payment-service",
        }
    )

    assert not isinstance(result, ParseFailure)
    assert result.log_level == "ERROR"
    assert any("log.level" in warning for warning in result.warnings)


def test_missing_required_field_rejected() -> None:
    """Missing required ECS fields should fail validation."""
    result = parse_event(
        {
            "@timestamp": "2026-06-30T12:01:00Z",
            "log.level": "ERROR",
            "message": "Payment timeout",
        }
    )

    assert isinstance(result, ParseFailure)
    assert "service.name" in result.message


def test_malformed_json_line_rejected() -> None:
    """Malformed JSONL lines should fail parsing."""
    result = parse_json_line("{not-json", line_number=3)

    assert isinstance(result, ParseFailure)
    assert result.source_index == 3


def test_invalid_timestamp_rejected() -> None:
    """Invalid timestamps should fail validation."""
    result = parse_event(
        {
            "@timestamp": "not-a-date",
            "log.level": "ERROR",
            "message": "Payment timeout",
            "service.name": "payment-service",
        }
    )

    assert isinstance(result, ParseFailure)
    assert "timestamp" in result.message.lower()


def test_parse_event_normalizes_optional_dotted_fields() -> None:
    """Parser should normalize optional ECS fields from dotted keys."""
    result = parse_event(
        {
            "@timestamp": "2026-06-30T12:01:00Z",
            "log.level": "ERROR",
            "message": "Payment timeout",
            "service.name": "payment-service",
            "event.id": "evt-123",
            "event.dataset": "payment.transaction",
            "event.outcome": "failure",
            "event.duration": 456326283,
            "trace.id": "trace-abc",
            "span.id": "span-def",
            "transaction.id": "txn-ghi",
            "error.type": "UpstreamTimeout",
            "error.message": "Provider timed out",
            "http.response.status_code": "502",
        }
    )

    assert not isinstance(result, ParseFailure)
    assert result.event_id == "evt-123"
    assert result.event_dataset == "payment.transaction"
    assert result.event_outcome == "failure"
    assert result.event_duration_ns == 456326283
    assert result.trace_id == "trace-abc"
    assert result.span_id == "span-def"
    assert result.transaction_id == "txn-ghi"
    assert result.error_type == "UpstreamTimeout"
    assert result.error_message == "Provider timed out"
    assert result.http_status_code == 502
    assert result.timestamp.tzinfo == timezone.utc


def test_parse_event_normalizes_optional_nested_fields() -> None:
    """Parser should normalize optional ECS fields from nested objects."""
    result = parse_event(
        {
            "@timestamp": "2026-06-30T12:01:00Z",
            "log": {"level": "ERROR"},
            "message": "Payment timeout",
            "service": {"name": "payment-service"},
            "event": {
                "id": "evt-456",
                "dataset": "payment.transaction",
                "outcome": "failure",
                "duration": 100000000,
            },
            "trace": {"id": "trace-nested"},
            "span": {"id": "span-nested"},
            "transaction": {"id": "txn-nested"},
            "error": {"type": "GatewayError", "message": "Bad gateway"},
        }
    )

    assert not isinstance(result, ParseFailure)
    assert result.event_id == "evt-456"
    assert result.event_dataset == "payment.transaction"
    assert result.event_outcome == "failure"
    assert result.event_duration_ns == 100000000
    assert result.trace_id == "trace-nested"
    assert result.span_id == "span-nested"
    assert result.transaction_id == "txn-nested"
    assert result.error_type == "GatewayError"
    assert result.error_message == "Bad gateway"


@pytest.mark.parametrize(
    ("missing_field",),
    [
        ("@timestamp",),
        ("log.level",),
        ("message",),
        ("service.name",),
    ],
)
def test_missing_required_field_rejected_parameterized(missing_field: str) -> None:
    """Each required ECS field should fail validation when missing."""
    event = {
        "@timestamp": "2026-06-30T12:01:00Z",
        "log.level": "ERROR",
        "message": "Payment timeout",
        "service.name": "payment-service",
    }
    event.pop(missing_field)

    result = parse_event(event)

    assert isinstance(result, ParseFailure)
    assert missing_field in result.message
