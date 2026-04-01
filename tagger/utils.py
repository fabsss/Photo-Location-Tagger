"""Utility functions for coordinate and timezone handling."""

from datetime import datetime, timedelta, timezone


def normalize_point_string(raw_point: str) -> str:
    """Strip encoding artifacts and unit symbols from coordinate string.

    Handles:
    - Unicode degree symbol: °
    - Mis-decoded UTF-8 as Latin-1: Â
    - Geo URI prefix: geo:

    Args:
        raw_point: Raw coordinate string, e.g. "52.5145434°, 13.3275447°"

    Returns:
        Cleaned string, e.g. "52.5145434, 13.3275447"
    """
    return raw_point.replace("°", "").replace("Â", "").replace("geo:", "").strip()


def apply_timezone_offset(dt: datetime | None, offset_minutes: int | None) -> datetime | None:
    """Convert datetime to correct timezone using offset in minutes.

    The input datetime may have an incorrect timezone offset in its string representation
    (e.g., from Google's export). This function converts it to UTC first, then applies
    the correct offset from the authoritative startTimeTimezoneUtcOffsetMinutes field.

    Args:
        dt: Timezone-aware or naive datetime
        offset_minutes: Correct UTC offset in minutes (e.g., 660 for UTC+11)

    Returns:
        Timezone-aware datetime with correct offset, or None if inputs invalid

    Example:
        Input: "2025-12-12T14:43:06+01:00" (wrong offset) + 660 minutes (UTC+11)
        Output: "2025-12-13T00:43:06+11:00" (correct local time in Melbourne)
    """
    if dt is None or offset_minutes is None:
        return dt

    # Convert to UTC first (handles incorrect offset in the original string)
    if dt.tzinfo is not None:
        dt_utc = dt.astimezone(timezone.utc)
    else:
        # If naive, assume it's UTC
        dt_utc = dt.replace(tzinfo=timezone.utc)

    # Apply the correct offset in minutes
    offset_hours = offset_minutes / 60
    target_tz = timezone(timedelta(hours=offset_hours))
    dt_target = dt_utc.astimezone(target_tz)
    return dt_target
