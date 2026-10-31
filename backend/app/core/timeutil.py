"""Timezone helpers. All business logic works on timezone-aware UTC datetimes."""

from datetime import datetime, timezone

UTC = timezone.utc  # datetime.UTC was added in Python 3.11; timezone.utc works everywhere



def as_utc(dt: datetime) -> datetime:
    """Return ``dt`` as aware UTC; naive values (e.g. read back from SQLite) are assumed UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def utcnow() -> datetime:
    """Current time, aware UTC."""
    return datetime.now(UTC)
