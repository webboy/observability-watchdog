"""Time bucket helpers for metric aggregation."""

from datetime import datetime, timedelta, timezone

WINDOW_MINUTES = 10


def floor_to_window_start(timestamp: datetime, window_minutes: int = WINDOW_MINUTES) -> datetime:
    """Floor a timestamp to the start of a fixed UTC bucket."""
    ts = timestamp.astimezone(timezone.utc)
    floored_minute = (ts.minute // window_minutes) * window_minutes
    return ts.replace(minute=floored_minute, second=0, microsecond=0)


def window_end_from_start(window_start: datetime, window_minutes: int = WINDOW_MINUTES) -> datetime:
    """Return the exclusive end timestamp for a bucket."""
    return window_start + timedelta(minutes=window_minutes)


def iter_window_starts(
    min_timestamp: datetime,
    max_timestamp: datetime,
    window_minutes: int = WINDOW_MINUTES,
) -> list[datetime]:
    """Return all bucket starts covering the timestamp range."""
    start = floor_to_window_start(min_timestamp, window_minutes)
    end = floor_to_window_start(max_timestamp, window_minutes)
    buckets: list[datetime] = []
    current = start
    while current <= end:
        buckets.append(current)
        current += timedelta(minutes=window_minutes)
    return buckets
