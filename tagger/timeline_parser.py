"""Parse Google Timeline JSON to extract GPS points with timezone information."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dateutil import parser as dateutil_parser

from .utils import normalize_point_string, apply_timezone_offset


logger = logging.getLogger(__name__)


class TimelineParseError(Exception):
    """Raised when timeline.json cannot be parsed or is invalid."""

    pass


@dataclass
class GPSPoint:
    """A GPS coordinate with timestamp and timezone information."""

    utc_time: datetime  # always UTC-aware (timezone.utc)
    local_time: datetime  # naive: utc_time + tz_offset, for matching image timestamps
    lat: float
    lon: float
    tz_offset_minutes: int  # e.g., 660 for UTC+11
    tz_offset_str: str  # e.g., "+11:00" for EXIF OffsetTimeOriginal tag

    def __lt__(self, other):
        """Enable sorting by local_time."""
        return self.local_time < other.local_time


def load_timeline(timeline_path: str | Path) -> list[GPSPoint]:
    """Load and parse Google Timeline JSON, extracting GPS points.

    Detects and handles multiple timeline.json formats:
    - semanticSegments: Modern format with explicit timezone offset field
    - locations: Legacy format with timestampMs (Unix epoch)
    - timelineObjects: Older format with activity/visit objects

    Args:
        timeline_path: Path to timeline.json file

    Returns:
        Sorted list of GPSPoint objects by local_time

    Raises:
        TimelineParseError: If JSON is malformed, file not found, or no usable points found

    Example:
        points = load_timeline("timeline.json")
        for point in points:
            print(f"{point.lat}, {point.lon} at {point.local_time}")
    """
    try:
        with open(timeline_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise TimelineParseError(f"Timeline file not found: {timeline_path}")
    except json.JSONDecodeError as e:
        raise TimelineParseError(f"Invalid JSON in timeline file: {e}")

    points = []

    # Detect format and parse accordingly
    if isinstance(data, dict):
        if "semanticSegments" in data:
            points.extend(_parse_semantic_segments(data))
        elif "locations" in data:
            points.extend(_parse_legacy_locations(data))
        elif "timelineObjects" in data:
            points.extend(_parse_timeline_objects(data["timelineObjects"]))
    elif isinstance(data, list):
        points.extend(_parse_timeline_objects(data))

    if not points:
        logger.warning("No usable GPS points found in timeline")
        raise TimelineParseError("No GPS points extracted from timeline")

    # Sort by local_time for binary search in location_finder
    points.sort()
    logger.info(f"Loaded {len(points)} GPS points from timeline")
    return points


def _parse_semantic_segments(data: dict) -> list[GPSPoint]:
    """Parse modern semanticSegments format."""
    points = []
    for segment in data.get("semanticSegments", []):
        segment_offset_minutes = segment.get("startTimeTimezoneUtcOffsetMinutes")

        for path_point in segment.get("timelinePath", []):
            try:
                # Extract and normalize coordinates
                raw_coords = normalize_point_string(path_point.get("point", ""))
                coords = [c.strip() for c in raw_coords.split(",") if c.strip()]
                if len(coords) < 2:
                    continue

                lat = float(coords[0])
                lon = float(coords[1])

                # Parse timestamp
                time_str = path_point.get("time")
                if not time_str:
                    continue

                utc_dt = dateutil_parser.isoparse(time_str)
                if utc_dt.tzinfo is None:
                    utc_dt = utc_dt.replace(tzinfo=timezone.utc)
                else:
                    utc_dt = utc_dt.astimezone(timezone.utc)

                # Apply correct timezone offset if available
                if segment_offset_minutes is not None:
                    local_dt = apply_timezone_offset(utc_dt, segment_offset_minutes)
                    tz_offset_str = _format_offset_string(segment_offset_minutes)
                else:
                    # Fall back to offset from the time string itself
                    local_dt = dateutil_parser.isoparse(time_str)
                    if local_dt.tzinfo is not None:
                        tz_offset_minutes = int(local_dt.utcoffset().total_seconds() // 60)
                        tz_offset_str = _format_offset_string(tz_offset_minutes)
                        local_dt = local_dt.replace(tzinfo=None)
                    else:
                        continue

                points.append(
                    GPSPoint(
                        utc_time=utc_dt,
                        local_time=local_dt.replace(tzinfo=None),
                        lat=lat,
                        lon=lon,
                        tz_offset_minutes=segment_offset_minutes or int(
                            dateutil_parser.isoparse(time_str).utcoffset().total_seconds() // 60
                        ),
                        tz_offset_str=tz_offset_str,
                    )
                )
            except (ValueError, KeyError, TypeError) as e:
                logger.debug(f"Skipped malformed point in semanticSegments: {e}")
                continue

    return points


def _parse_legacy_locations(data: dict) -> list[GPSPoint]:
    """Parse legacy locations format with timestampMs."""
    points = []
    for loc in data.get("locations", []):
        try:
            lat = float(loc.get("latitudeE7", 0)) / 1e7
            lon = float(loc.get("longitudeE7", 0)) / 1e7
            timestamp_ms = int(loc.get("timestampMs", 0))

            if lat == 0 and lon == 0:
                continue

            utc_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            local_dt = utc_dt.replace(tzinfo=None)

            # Legacy format doesn't include timezone offset, assume UTC
            points.append(
                GPSPoint(
                    utc_time=utc_dt,
                    local_time=local_dt,
                    lat=lat,
                    lon=lon,
                    tz_offset_minutes=0,
                    tz_offset_str="+00:00",
                )
            )
        except (ValueError, TypeError, AttributeError) as e:
            logger.debug(f"Skipped malformed location in legacy format: {e}")
            continue

    return points


def _parse_timeline_objects(data: list) -> list[GPSPoint]:
    """Parse timelineObjects format with activity/visit objects."""
    points = []
    for segment in data:
        if not isinstance(segment, dict):
            continue

        segment_offset_minutes = segment.get("startTimeTimezoneUtcOffsetMinutes")

        # Parse timelinePath if present
        for path_point in segment.get("timelinePath", []):
            try:
                raw_coords = normalize_point_string(path_point.get("point", ""))
                coords = [c.strip() for c in raw_coords.split(",") if c.strip()]
                if len(coords) < 2:
                    continue

                lat = float(coords[0])
                lon = float(coords[1])
                time_str = path_point.get("time")

                if not time_str:
                    continue

                utc_dt = dateutil_parser.isoparse(time_str)
                if utc_dt.tzinfo is None:
                    utc_dt = utc_dt.replace(tzinfo=timezone.utc)
                else:
                    utc_dt = utc_dt.astimezone(timezone.utc)

                if segment_offset_minutes is not None:
                    local_dt = apply_timezone_offset(utc_dt, segment_offset_minutes)
                    tz_offset_str = _format_offset_string(segment_offset_minutes)
                    tz_offset_minutes = segment_offset_minutes
                else:
                    local_dt = dateutil_parser.isoparse(time_str)
                    if local_dt.tzinfo is not None:
                        tz_offset_minutes = int(local_dt.utcoffset().total_seconds() // 60)
                        tz_offset_str = _format_offset_string(tz_offset_minutes)
                        local_dt = local_dt.replace(tzinfo=None)
                    else:
                        continue

                points.append(
                    GPSPoint(
                        utc_time=utc_dt,
                        local_time=local_dt.replace(tzinfo=None) if local_dt.tzinfo else local_dt,
                        lat=lat,
                        lon=lon,
                        tz_offset_minutes=tz_offset_minutes,
                        tz_offset_str=tz_offset_str,
                    )
                )
            except (ValueError, KeyError, TypeError) as e:
                logger.debug(f"Skipped malformed point in timelineObjects: {e}")
                continue

        # Parse activity/place visit entries
        for activity_key in ("activitySegment", "placeVisit"):
            activity = segment.get(activity_key)
            if not isinstance(activity, dict):
                continue

            try:
                start_timestamp = activity.get("duration", {}).get("startTimestamp")
                if not start_timestamp:
                    continue

                utc_dt = dateutil_parser.isoparse(start_timestamp)
                if utc_dt.tzinfo is None:
                    utc_dt = utc_dt.replace(tzinfo=timezone.utc)
                else:
                    utc_dt = utc_dt.astimezone(timezone.utc)

                if segment_offset_minutes is not None:
                    local_dt = apply_timezone_offset(utc_dt, segment_offset_minutes)
                    tz_offset_str = _format_offset_string(segment_offset_minutes)
                    tz_offset_minutes = segment_offset_minutes
                else:
                    local_dt = dateutil_parser.isoparse(start_timestamp)
                    if local_dt.tzinfo is not None:
                        tz_offset_minutes = int(local_dt.utcoffset().total_seconds() // 60)
                        tz_offset_str = _format_offset_string(tz_offset_minutes)
                        local_dt = local_dt.replace(tzinfo=None)
                    else:
                        continue

                location = activity.get("location", {})
                lat = float(location.get("latitudeE7", 0)) / 1e7
                lon = float(location.get("longitudeE7", 0)) / 1e7

                if lat == 0 and lon == 0:
                    continue

                points.append(
                    GPSPoint(
                        utc_time=utc_dt,
                        local_time=local_dt.replace(tzinfo=None) if local_dt.tzinfo else local_dt,
                        lat=lat,
                        lon=lon,
                        tz_offset_minutes=tz_offset_minutes,
                        tz_offset_str=tz_offset_str,
                    )
                )
            except (ValueError, KeyError, TypeError) as e:
                logger.debug(f"Skipped malformed activity in timelineObjects: {e}")
                continue

    return points


def _format_offset_string(offset_minutes: int) -> str:
    """Convert offset in minutes to ISO 8601 offset string.

    Args:
        offset_minutes: Offset from UTC in minutes (e.g., 660 for UTC+11, -300 for UTC-5)

    Returns:
        Offset string (e.g., "+11:00", "-05:00")
    """
    sign = "+" if offset_minutes >= 0 else "-"
    hours = abs(offset_minutes) // 60
    minutes = abs(offset_minutes) % 60
    return f"{sign}{hours:02d}:{minutes:02d}"
