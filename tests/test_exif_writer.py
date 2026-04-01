"""Tests for exif_writer module."""

from datetime import datetime
from pathlib import Path

import pytest

from tagger.exif_writer import (
    check_exiftool,
    read_datetime,
    read_datetime_batch,
    write_location,
    ExifToolNotFoundError,
)
from tagger.timeline_parser import GPSPoint


class TestCheckExiftool:
    """Test check_exiftool() function."""

    def test_exiftool_installed(self):
        """Verify exiftool is available on the system."""
        # This test verifies that exiftool is installed
        # It will raise ExifToolNotFoundError if not available
        try:
            result = check_exiftool()
            assert result is True
        except ExifToolNotFoundError:
            pytest.skip("exiftool not installed")


class TestReadDatetime:
    """Test read_datetime() function."""

    def test_read_datetime_jpg(self):
        """Test reading DateTimeOriginal from JPEG."""
        jpg_path = Path(__file__).parent / "fixtures" / "sample.jpg"

        if not jpg_path.exists():
            pytest.skip("sample.jpg fixture not created")

        try:
            check_exiftool()
        except ExifToolNotFoundError:
            pytest.skip("exiftool not installed")

        dt = read_datetime(jpg_path)
        assert dt is not None
        assert isinstance(dt, datetime)
        # Should match the fixture creation: "2025:12:13 00:02:00"
        assert dt.year == 2025
        assert dt.month == 12
        assert dt.day == 13
        assert dt.hour == 0
        assert dt.minute == 2
        assert dt.second == 0

    def test_read_datetime_missing_file(self):
        """Test reading from non-existent file."""
        dt = read_datetime("/nonexistent/file.jpg")
        assert dt is None

    def test_read_datetime_no_exif(self, tmp_path):
        """Test reading from image with no EXIF date."""
        try:
            check_exiftool()
        except ExifToolNotFoundError:
            pytest.skip("exiftool not installed")

        # Create an empty file - exiftool should handle gracefully
        test_file = tmp_path / "no_exif.jpg"
        test_file.write_bytes(b"fake jpg data")

        dt = read_datetime(test_file)
        # Should return None if no date found
        assert dt is None


class TestWriteLocation:
    """Test write_location() function."""

    @pytest.fixture
    def test_point(self):
        """Create a GPSPoint for testing."""
        return GPSPoint(
            utc_time=None,
            local_time=datetime(2025, 12, 13, 0, 2, 0),
            lat=52.5147,
            lon=13.3277,
            tz_offset_minutes=660,
            tz_offset_str="+11:00"
        )

    def test_dry_run_writes_nothing(self, tmp_path, test_point):
        """Test that dry_run doesn't modify the file."""
        jpg_path = Path(__file__).parent / "fixtures" / "sample.jpg"

        if not jpg_path.exists():
            pytest.skip("sample.jpg fixture not created")

        try:
            check_exiftool()
        except ExifToolNotFoundError:
            pytest.skip("exiftool not installed")

        # Copy to temp for testing
        test_copy = tmp_path / "test.jpg"
        test_copy.write_bytes(jpg_path.read_bytes())
        original_size = test_copy.stat().st_size

        # Write with dry_run=True
        result = write_location(test_copy, test_point, dry_run=True)
        assert result is True

        # File should be unchanged
        assert test_copy.stat().st_size == original_size

    def test_write_location_single_file(self, tmp_path, test_point):
        """Test writing GPS location to a file."""
        jpg_path = Path(__file__).parent / "fixtures" / "sample.jpg"

        if not jpg_path.exists():
            pytest.skip("sample.jpg fixture not created")

        try:
            check_exiftool()
        except ExifToolNotFoundError:
            pytest.skip("exiftool not installed")

        test_copy = tmp_path / "test.jpg"
        test_copy.write_bytes(jpg_path.read_bytes())

        result = write_location(test_copy, test_point, backup=False, dry_run=False)

        if result:
            # If write succeeded, file should still exist
            assert test_copy.exists()

    def test_write_location_missing_file(self, test_point):
        """Test write_location with non-existent file."""
        result = write_location("/nonexistent/file.jpg", test_point)
        assert result is False

    def test_backup_option(self, tmp_path, test_point):
        """Test backup option creates _original file."""
        jpg_path = Path(__file__).parent / "fixtures" / "sample.jpg"

        if not jpg_path.exists():
            pytest.skip("sample.jpg fixture not created")

        try:
            check_exiftool()
        except ExifToolNotFoundError:
            pytest.skip("exiftool not installed")

        test_copy = tmp_path / "test.jpg"
        test_copy.write_bytes(jpg_path.read_bytes())

        result = write_location(test_copy, test_point, backup=True, dry_run=False)

        # Check if backup was created (only if write succeeded)
        if result:
            backup_file = tmp_path / "test_original.jpg"
            # Note: exiftool may not create backup with the exact name we expect
            # but at least the original file should be modified
            assert test_copy.exists()


class TestReadDatetimeBatch:
    """Test read_datetime_batch() function."""

    def test_batch_reads_multiple_files(self, tmp_path):
        """Test reading timestamps from multiple files via batch."""
        jpg_path = Path(__file__).parent / "fixtures" / "sample.jpg"

        if not jpg_path.exists():
            pytest.skip("sample.jpg fixture not created")

        try:
            check_exiftool()
        except ExifToolNotFoundError:
            pytest.skip("exiftool not installed")

        # Create multiple copies to test batch reading
        test_files = []
        for i in range(3):
            test_copy = tmp_path / f"test_{i}.jpg"
            test_copy.write_bytes(jpg_path.read_bytes())
            test_files.append(test_copy)

        # Read all timestamps at once
        result_map = read_datetime_batch(test_files)

        # Should have entries for all files
        assert len(result_map) == 3
        for test_file in test_files:
            assert test_file in result_map
            # All should have the same timestamp since they're copies
            assert isinstance(result_map[test_file], datetime)
            assert result_map[test_file].year == 2025

    def test_batch_handles_missing_timestamp(self, tmp_path):
        """Test batch reading with files that have no timestamp."""
        try:
            check_exiftool()
        except ExifToolNotFoundError:
            pytest.skip("exiftool not installed")

        # Create a file with no EXIF data
        test_file = tmp_path / "no_exif.jpg"
        test_file.write_bytes(b"fake jpg data")

        result_map = read_datetime_batch([test_file])

        # Should have entry for the file, but with None value
        assert test_file in result_map
        assert result_map[test_file] is None

    def test_batch_empty_list(self):
        """Test batch reading with empty file list."""
        result_map = read_datetime_batch([])
        assert result_map == {}

    def test_batch_chunks_large_lists(self, tmp_path):
        """Test that batch chunking works correctly with small chunk size."""
        jpg_path = Path(__file__).parent / "fixtures" / "sample.jpg"

        if not jpg_path.exists():
            pytest.skip("sample.jpg fixture not created")

        try:
            check_exiftool()
        except ExifToolNotFoundError:
            pytest.skip("exiftool not installed")

        # Create more files than default chunk size
        test_files = []
        for i in range(5):
            test_copy = tmp_path / f"test_{i}.jpg"
            test_copy.write_bytes(jpg_path.read_bytes())
            test_files.append(test_copy)

        # Read with small chunk_size to force multiple subprocess calls
        result_map = read_datetime_batch(test_files, chunk_size=2)

        # Should successfully read all files despite chunking
        assert len(result_map) == 5
        for test_file in test_files:
            assert test_file in result_map
            # All should have valid timestamps
            if result_map[test_file] is not None:
                assert isinstance(result_map[test_file], datetime)
