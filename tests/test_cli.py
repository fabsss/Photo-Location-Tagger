"""Tests for CLI utilities."""

from pathlib import Path

import pytest

# Import from parent directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from tagger_cli import get_unique_log_path


class TestGetUniqueLogPath:
    """Test get_unique_log_path() function."""

    def test_nonexistent_file_returns_original_path(self, tmp_path):
        """Test that nonexistent file returns the original path."""
        log_path = tmp_path / "test.log"
        assert not log_path.exists()

        result = get_unique_log_path(log_path)
        assert result == log_path

    def test_existing_file_returns_numbered_path(self, tmp_path):
        """Test that existing file gets .1 appended."""
        log_path = tmp_path / "test.log"
        log_path.touch()  # Create the file

        result = get_unique_log_path(log_path)
        assert result == tmp_path / "test.log.1"
        assert not result.exists()

    def test_multiple_existing_files_increments_counter(self, tmp_path):
        """Test that multiple existing files get incremented counters."""
        log_path = tmp_path / "test.log"

        # Create original log and numbered versions
        log_path.touch()
        (tmp_path / "test.log.1").touch()
        (tmp_path / "test.log.2").touch()

        result = get_unique_log_path(log_path)
        assert result == tmp_path / "test.log.3"
        assert not result.exists()

    def test_finds_gap_in_numbering(self, tmp_path):
        """Test that function returns first available number."""
        log_path = tmp_path / "test.log"

        # Create original log and numbered versions (with gap)
        log_path.touch()
        (tmp_path / "test.log.1").touch()
        (tmp_path / "test.log.2").touch()
        (tmp_path / "test.log.4").touch()

        result = get_unique_log_path(log_path)
        assert result == tmp_path / "test.log.3"
        assert not result.exists()
