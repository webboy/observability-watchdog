"""ECS-compatible log event parser and normalizer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


REQUIRED_ECS_FIELDS = ("@timestamp", "log.level", "message", "service.name")

OPTIONAL_FIELD_MAP = {
    "event.id": "event_id",
    "event.dataset": "event_dataset",
    "event.outcome": "event_outcome",
    "event.duration": "event_duration_ns",
    "http.response.status_code": "http_status_code",
    "url.path": "url_path",
    "trace.id": "trace_id",
    "span.id": "span_id",
    "transaction.id": "transaction_id",
    "error.type": "error_type",
    "error.message": "error_message",
}


@dataclass(slots=True)
class ParsedLogEvent:
    """Normalized log event ready for dedupe and persistence."""

    timestamp: datetime
    service_name: str
    log_level: str
    message: str
    raw_event_json: dict[str, Any]
    event_id: str | None = None
    event_dataset: str | None = None
    event_outcome: str | None = None
    event_duration_ns: int | None = None
    http_status_code: int | None = None
    url_path: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    transaction_id: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    warnings: list[str] = field(default_factory=list)
    source_index: int | None = None


@dataclass(slots=True)
class ParseFailure:
    """Validation or parsing failure for one event."""

    message: str
    source_index: int | None = None


ParseResult = ParsedLogEvent | ParseFailure


def _get_nested_value(raw_event: dict[str, Any], dotted_key: str) -> Any | None:
    """Resolve a dotted ECS key from nested JSON objects."""
    current: Any = raw_event
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def get_ecs_value(raw_event: dict[str, Any], dotted_key: str) -> tuple[Any | None, bool]:
    """Return an ECS field value, preferring flat dotted keys over nested objects."""
    dotted_present = dotted_key in raw_event
    nested_value = _get_nested_value(raw_event, dotted_key)

    if dotted_present:
        return raw_event[dotted_key], False
    if nested_value is not None:
        return nested_value, True
    return None, False


def _coerce_optional_int(value: Any, field_name: str) -> int | None:
    """Coerce optional integer ECS fields."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer for {field_name}") from exc


def _parse_timestamp(value: Any) -> datetime:
    """Parse ECS @timestamp into a timezone-aware UTC datetime."""
    if not isinstance(value, str):
        raise ValueError("@timestamp must be a string")

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("Invalid @timestamp format") from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_event(raw_event: dict[str, Any], source_index: int | None = None) -> ParseResult:
    """Parse and normalize one ECS-compatible event object."""
    if not isinstance(raw_event, dict):
        return ParseFailure(message="Event must be a JSON object", source_index=source_index)

    warnings: list[str] = []

    for ecs_key in REQUIRED_ECS_FIELDS:
        dotted_present = ecs_key in raw_event
        nested_value = _get_nested_value(raw_event, ecs_key)
        if dotted_present and nested_value is not None and raw_event.get(ecs_key) != nested_value:
            warnings.append(f"Field '{ecs_key}' uses dotted key value over nested object value")

    missing = [
        ecs_key
        for ecs_key in REQUIRED_ECS_FIELDS
        if get_ecs_value(raw_event, ecs_key)[0] in (None, "")
    ]
    if missing:
        return ParseFailure(
            message=f"Missing required field(s): {', '.join(missing)}",
            source_index=source_index,
        )

    try:
        timestamp = _parse_timestamp(get_ecs_value(raw_event, "@timestamp")[0])
        log_level = str(get_ecs_value(raw_event, "log.level")[0])
        message = str(get_ecs_value(raw_event, "message")[0])
        service_name = str(get_ecs_value(raw_event, "service.name")[0])
    except ValueError as exc:
        return ParseFailure(message=str(exc), source_index=source_index)

    optional_values: dict[str, Any] = {}
    for ecs_key, internal_name in OPTIONAL_FIELD_MAP.items():
        dotted_present = ecs_key in raw_event
        nested_value = _get_nested_value(raw_event, ecs_key)
        if dotted_present and nested_value is not None and raw_event[ecs_key] != nested_value:
            warnings.append(f"Field '{ecs_key}' uses dotted key value over nested object value")

        value, _ = get_ecs_value(raw_event, ecs_key)
        if value is None or value == "":
            optional_values[internal_name] = None
            continue

        if internal_name in {"event_duration_ns", "http_status_code"}:
            try:
                optional_values[internal_name] = _coerce_optional_int(value, ecs_key)
            except ValueError as exc:
                return ParseFailure(message=str(exc), source_index=source_index)
        else:
            optional_values[internal_name] = str(value)

    return ParsedLogEvent(
        timestamp=timestamp,
        service_name=service_name,
        log_level=log_level,
        message=message,
        raw_event_json=raw_event,
        warnings=warnings,
        source_index=source_index,
        **optional_values,
    )


def parse_json_line(line: str, line_number: int) -> ParseResult:
    """Parse one JSONL line into a normalized event."""
    stripped = line.strip()
    if not stripped:
        return ParseFailure(message="Empty line", source_index=line_number)

    try:
        raw_event = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return ParseFailure(message=f"Malformed JSON: {exc.msg}", source_index=line_number)

    return parse_event(raw_event, source_index=line_number)
