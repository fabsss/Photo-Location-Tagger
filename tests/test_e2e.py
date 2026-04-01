"""End-to-end tests for the complete geotagging pipeline."""

import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from tagger.timeline_parser import load_timeline
from tagger.location_finder import find_closest
from tagger.exif_writer import read_datetime, write_location, check_exiftool


class TestE2EPipeline:
    """End-to-end tests for the complete pipeline."""

    @pytest.fixture(autouse=True)
    def verify_exiftool(self):
        """Skip all tests if exiftool is not available."""
        try:
            check_exiftool()
        except Exception:
            pytest.skip("exiftool not installed")

    def test_full_pipeline_jpg(self, tmp_path):
        """Test complete pipeline: load timeline → read image → find GPS → write location."""
        # Setup: copy fixtures to temp directory
        sample_jpg = Path(__file__).parent / "fixtures" / "sample.jpg"
        sample_timeline = Path(__file__).parent / "fixtures" / "sample_timeline.json"
        
        if not sample_jpg.exists() or not sample_timeline.exists():
            pytest.skip("Required fixtures not created")
        
        test_jpg = tmp_path / "test.jpg"
        test_jpg.write_bytes(sample_jpg.read_bytes())
        
        # Step 1: Load timeline
        timeline_points = load_timeline(sample_timeline)
        assert len(timeline_points) > 0
        
        # Step 2: Read image timestamp
        image_dt = read_datetime(test_jpg)
        assert image_dt is not None
        assert image_dt.hour == 0
        assert image_dt.minute == 2
        
        # Step 3: Find closest GPS point
        point = find_closest(image_dt, timeline_points, max_delta_minutes=30)
        assert point is not None
        assert point.lat == 52.5147
        assert point.lon == 13.3277
        assert point.tz_offset_str == "+11:00"
        
        # Step 4: Write location to image
        success = write_location(test_jpg, point, backup=False, dry_run=False)
        assert success is True
        
        # Verify the GPS tags were written using exiftool
        result = subprocess.run(
            ["exiftool", "-GPSLatitude", "-GPSLongitude", "-s3", str(test_jpg)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode == 0:
            output = result.stdout.strip()
            # Output format varies, but should contain coordinates
            assert "52" in output or "13" in output

    def test_no_match_skips_file(self, tmp_path):
        """Test that files without GPS matches are skipped."""
        sample_jpg = Path(__file__).parent / "fixtures" / "sample.jpg"
        sample_timeline = Path(__file__).parent / "fixtures" / "sample_timeline.json"
        
        if not sample_jpg.exists() or not sample_timeline.exists():
            pytest.skip("Required fixtures not created")
        
        test_jpg = tmp_path / "test.jpg"
        test_jpg.write_bytes(sample_jpg.read_bytes())
        
        # Load timeline
        timeline_points = load_timeline(sample_timeline)
        
        # Create an image time far in the past (2 hours before any GPS point)
        far_past_time = datetime(2025, 12, 12, 22, 0, 0)
        
        # Try to find a match with a very small time margin
        point = find_closest(far_past_time, timeline_points, max_delta_minutes=30)
        assert point is None

    def test_dry_run_writes_nothing(self, tmp_path):
        """Test that dry_run mode doesn't modify files."""
        sample_jpg = Path(__file__).parent / "fixtures" / "sample.jpg"
        sample_timeline = Path(__file__).parent / "fixtures" / "sample_timeline.json"
        
        if not sample_jpg.exists() or not sample_timeline.exists():
            pytest.skip("Required fixtures not created")
        
        test_jpg = tmp_path / "test.jpg"
        test_jpg.write_bytes(sample_jpg.read_bytes())
        original_size = test_jpg.stat().st_size
        
        # Load and process with dry_run=True
        timeline_points = load_timeline(sample_timeline)
        image_dt = read_datetime(test_jpg)
        assert image_dt is not None
        
        point = find_closest(image_dt, timeline_points, max_delta_minutes=30)
        assert point is not None
        
        success = write_location(test_jpg, point, backup=False, dry_run=True)
        assert success is True
        
        # File should be unchanged
        assert test_jpg.stat().st_size == original_size

    def test_malformed_json_exits_gracefully(self, tmp_path):
        """Test handling of malformed JSON timeline."""
        from tagger.timeline_parser import TimelineParseError
        
        bad_json = tmp_path / "bad_timeline.json"
        bad_json.write_text("{ this is not valid json }")
        
        with pytest.raises(TimelineParseError):
            load_timeline(bad_json)
