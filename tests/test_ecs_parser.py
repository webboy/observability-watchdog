"""ECS parser unit tests."""

from datetime import timezone

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
