"""Deduplication key generation for log events."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from app.services.ecs_parser import ParsedLogEvent


def _sha256_hex(value: str) -> str:
    """Return SHA-256 hex digest for a string payload."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_payload(app_id: uuid.UUID, parsed: ParsedLogEvent) -> dict[str, Any]:
    """Build the canonical dedupe payload from normalized event fields."""
    return {
        "app_id": str(app_id),
        "timestamp": parsed.timestamp.isoformat(),
        "service_name": parsed.service_name,
        "log_level": parsed.log_level,
        "message": parsed.message,
        "event_dataset": parsed.event_dataset,
        "event_outcome": parsed.event_outcome,
        "event_duration_ns": parsed.event_duration_ns,
        "http_status_code": parsed.http_status_code,
        "url_path": parsed.url_path,
        "trace_id": parsed.trace_id,
        "span_id": parsed.span_id,
        "transaction_id": parsed.transaction_id,
        "error_type": parsed.error_type,
        "error_message": parsed.error_message,
    }


def generate_dedupe_key(app_id: uuid.UUID, parsed: ParsedLogEvent) -> str:
    """Generate a stable dedupe key for one parsed log event."""
    if parsed.event_id:
        payload = f"event_id:{app_id}:{parsed.event_id}"
        return _sha256_hex(payload)

    canonical = _canonical_payload(app_id, parsed)
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return _sha256_hex(serialized)
