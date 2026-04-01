"""Find GPS locations matching image timestamps using binary search."""

import bisect
import logging
from datetime import datetime, timedelta

from .timeline_parser import GPSPoint


logger = logging.getLogger(__name__)


def find_closest(
    image_local_time: datetime,
    points: list[GPSPoint],
    max_delta_minutes: int = 30,
) -> GPSPoint | None:
    """Find the closest GPS point to an image's local timestamp.

    Uses binary search (bisect) on the pre-sorted points list for O(log n) lookup.
    Compares naive local times directly—no timezone conversion needed.

    Args:
        image_local_time: Image timestamp (naive datetime, e.g., from EXIF DateTimeOriginal)
        points: Sorted list of GPSPoint objects (must be sorted by local_time)
        max_delta_minutes: Maximum acceptable time difference in minutes.
                          If closest point exceeds this, returns None.

    Returns:
        Closest GPSPoint if within tolerance, else None

    Example:
        image_time = datetime.fromisoformat("2025-12-13 00:43:06")
        point = find_closest(image_time, gps_points, max_delta_minutes=30)
        if point:
            print(f"Found match: {point.lat}, {point.lon}")
        else:
            print("No GPS match within 30 minutes")
    """
    if not points:
        return None

    # Use bisect to find insertion point (O(log n))
    # This gives us the index where image_local_time would go in the sorted list
    idx = bisect.bisect_left(points, GPSPoint(None, image_local_time, 0, 0, 0, ""))

    # Check both the point at idx and the one before it (neighbours of the insertion point)
    candidates = []
    if idx > 0:
        candidates.append(points[idx - 1])
    if idx < len(points):
        candidates.append(points[idx])

    if not candidates:
        return None

    # Find the closest candidate
    closest_point = None
    min_delta = timedelta(minutes=max_delta_minutes + 1)  # Start higher than threshold

    for point in candidates:
        delta = abs(image_local_time - point.local_time)
        if delta < min_delta:
            min_delta = delta
            closest_point = point

    # Check if closest point is within tolerance
    if closest_point and min_delta <= timedelta(minutes=max_delta_minutes):
        return closest_point

    # No match within tolerance
    if closest_point:
        logger.warning(
            f"No GPS match for {image_local_time.isoformat()}: closest point is "
            f"{closest_point.local_time.isoformat()} ({int(min_delta.total_seconds() / 60)} min away, "
            f"limit is {max_delta_minutes} min)"
        )
    else:
        logger.warning(f"No GPS points available to match {image_local_time.isoformat()}")

    return None
