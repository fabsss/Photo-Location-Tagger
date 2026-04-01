"""Tests for location_finder module."""

from datetime import datetime

import pytest

from tagger.location_finder import find_closest
from tagger.timeline_parser import GPSPoint


@pytest.fixture
def sample_points():
    """Create a list of GPSPoints for testing."""
    return [
        GPSPoint(
            utc_time=None,
            local_time=datetime(2025, 12, 13, 0, 0, 0),
            lat=52.5145,
            lon=13.3275,
            tz_offset_minutes=660,
            tz_offset_str="+11:00"
        ),
        GPSPoint(
            utc_time=None,
            local_time=datetime(2025, 12, 13, 0, 1, 0),
            lat=52.5146,
            lon=13.3276,
            tz_offset_minutes=660,
            tz_offset_str="+11:00"
        ),
        GPSPoint(
            utc_time=None,
            local_time=datetime(2025, 12, 13, 0, 2, 0),
            lat=52.5147,
            lon=13.3277,
            tz_offset_minutes=660,
            tz_offset_str="+11:00"
        ),
        GPSPoint(
            utc_time=None,
            local_time=datetime(2025, 12, 13, 0, 3, 0),
            lat=52.5148,
            lon=13.3278,
            tz_offset_minutes=660,
            tz_offset_str="+11:00"
        ),
        GPSPoint(
            utc_time=None,
            local_time=datetime(2025, 12, 13, 0, 4, 0),
            lat=52.5149,
            lon=13.3279,
            tz_offset_minutes=660,
            tz_offset_str="+11:00"
        ),
    ]


class TestFindClosest:
    """Test find_closest() function."""

    def test_exact_match(self, sample_points):
        """Test when image time matches a GPS point exactly."""
        image_time = datetime(2025, 12, 13, 0, 2, 0)
        point = find_closest(image_time, sample_points, max_delta_minutes=30)
        
        assert point is not None
        assert point.local_time == image_time
        assert point.lat == 52.5147
        assert point.lon == 13.3277

    def test_within_margin(self, sample_points):
        """Test when closest point is within time margin."""
        # 25 minutes away, margin is 30
        image_time = datetime(2025, 12, 13, 0, 27, 0)
        point = find_closest(image_time, sample_points, max_delta_minutes=30)
        
        assert point is not None
        # Should find the 00:04:00 point (23 min away) or 00:02:00 (25 min away)
        # The closest is at 00:04:00, which is 23 minutes away
        assert abs((point.local_time - image_time).total_seconds() / 60) <= 30

    def test_outside_margin(self, sample_points):
        """Test when no point is within time margin."""
        # 35 minutes away from any point
        image_time = datetime(2025, 12, 13, 1, 9, 0)
        point = find_closest(image_time, sample_points, max_delta_minutes=30)
        
        assert point is None

    def test_empty_points(self):
        """Test with empty GPS points list."""
        image_time = datetime(2025, 12, 13, 0, 2, 0)
        point = find_closest(image_time, [], max_delta_minutes=30)
        
        assert point is None

    def test_single_point_match(self, sample_points):
        """Test with only one point in list."""
        single_point = [sample_points[2]]
        image_time = datetime(2025, 12, 13, 0, 2, 0)
        point = find_closest(image_time, single_point, max_delta_minutes=30)
        
        assert point is not None
        assert point == single_point[0]

    def test_single_point_no_match(self, sample_points):
        """Test with one point outside margin."""
        single_point = [sample_points[0]]
        image_time = datetime(2025, 12, 13, 1, 0, 0)
        point = find_closest(image_time, single_point, max_delta_minutes=30)
        
        assert point is None

    def test_finds_closest_of_two_neighbours(self, sample_points):
        """Test that finds the closest of two neighbours."""
        # Between 00:02:00 and 00:03:00, closer to 00:02:00
        image_time = datetime(2025, 12, 13, 0, 2, 20)
        point = find_closest(image_time, sample_points, max_delta_minutes=30)
        
        assert point is not None
        assert point.local_time == datetime(2025, 12, 13, 0, 2, 0)

    def test_zero_margin(self, sample_points):
        """Test with zero minute margin (exact match only)."""
        image_time = datetime(2025, 12, 13, 0, 2, 0)
        point = find_closest(image_time, sample_points, max_delta_minutes=0)
        
        assert point is not None
        assert point.local_time == image_time

    def test_zero_margin_no_match(self, sample_points):
        """Test with zero margin when no exact match."""
        image_time = datetime(2025, 12, 13, 0, 2, 30)
        point = find_closest(image_time, sample_points, max_delta_minutes=0)
        
        assert point is None
