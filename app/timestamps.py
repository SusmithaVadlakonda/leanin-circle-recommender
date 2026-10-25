"""Timestamps as the data stores them: ISO 8601 in UTC, millisecond precision, Z suffix."""
from datetime import datetime, timezone


def parse_timestamp(value: str) -> datetime:
    """Parse a stored timestamp into a timezone-aware UTC datetime."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def format_timestamp(value: datetime) -> str:
    """Format a datetime the way the data does, so stored strings compare correctly."""
    utc = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"
