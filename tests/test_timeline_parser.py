"""Tests for timeline_parser module."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tagger.timeline_parser import load_timeline, GPSPoint, TimelineParseError


@pytest.fixture
def sample_timeline_path():
    """Path to sample timeline fixture."""
    return Path(__file__).parent / "fixtures" / "sample_timeline.json"


@pytest.fixture
def sample_timeline_data():
    """Load sample timeline data."""
    with open(Path(__file__).parent / "fixtures" / "sample_timeline.json") as f:
        return json.load(f)


class TestLoadTimeline:
    """Test load_timeline() function."""

    def test_loads_semantic_segments(self, sample_timeline_path):
        """Test loading modern semanticSegments format."""
        points = load_timeline(sample_timeline_path)
        assert len(points) == 5
        assert all(isinstance(p, GPSPoint) for p in points)

    def test_gps_point_fields(self, sample_timeline_path):
        """Test that GPSPoint has all required fields."""
        points = load_timeline(sample_timeline_path)
        point = points[2]  # Middle point (should match 13:02:00 UTC)
        
        # Verify all fields exist and have correct types
        assert isinstance(point.utc_time, datetime)
        assert isinstance(point.local_time, datetime)
        assert isinstance(point.lat, float)
        assert isinstance(point.lon, float)
        assert isinstance(point.tz_offset_minutes, int)
        assert isinstance(point.tz_offset_str, str)
        
        # utc_time should be aware, local_time should be naive
        assert point.utc_time.tzinfo is not None
        assert point.local_time.tzinfo is None

    def test_applies_correct_timezone(self, sample_timeline_path):
        """Verify timezone offset is correctly applied."""
        points = load_timeline(sample_timeline_path)
        
        # All points should have UTC+11 offset (660 minutes)
        assert all(p.tz_offset_minutes == 660 for p in points)
        assert all(p.tz_offset_str == "+11:00" for p in points)
        
        # UTC time 13:00 + 11 hours = local time 00:00 (next day)
        first_point = points[0]
        assert first_point.utc_time.hour == 13
        assert first_point.local_time.hour == 0
        assert first_point.local_time.day == 13  # Next day

    def test_sorted_by_local_time(self, sample_timeline_path):
        """Verify returned list is sorted by local_time."""
        points = load_timeline(sample_timeline_path)
        
        for i in range(len(points) - 1):
            assert points[i].local_time <= points[i + 1].local_time

    def test_file_not_found_raises(self):
        """Test FileNotFoundError handling."""
        with pytest.raises(TimelineParseError, match="not found"):
            load_timeline("nonexistent_file.json")

    def test_malformed_json_raises(self, tmp_path):
        """Test malformed JSON handling."""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{ invalid json }")
        
        with pytest.raises(TimelineParseError, match="Invalid JSON"):
            load_timeline(bad_json)

    def test_empty_timeline_raises(self, tmp_path):
        """Test empty timeline handling."""
        empty_timeline = tmp_path / "empty.json"
        empty_timeline.write_text('{"semanticSegments": []}')
        
        with pytest.raises(TimelineParseError, match="No GPS points"):
            load_timeline(empty_timeline)


class TestGPSPointComparison:
    """Test GPSPoint sorting."""

    def test_gps_point_less_than(self):
        """Test __lt__ comparison for sorting."""
        dt1 = datetime(2025, 12, 13, 0, 0, 0)
        dt2 = datetime(2025, 12, 13, 0, 1, 0)
        
        point1 = GPSPoint(utc_time=None, local_time=dt1, lat=0, lon=0, tz_offset_minutes=0, tz_offset_str="")
        point2 = GPSPoint(utc_time=None, local_time=dt2, lat=0, lon=0, tz_offset_minutes=0, tz_offset_str="")
        
        assert point1 < point2
        assert not point2 < point1
