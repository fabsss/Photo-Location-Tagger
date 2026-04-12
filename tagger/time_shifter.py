"""Parse and apply datetime shifts to image and video files via exiftool subprocess."""

import logging
import subprocess
from datetime import timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def _has_keys_creation_date(file_path: Path) -> bool:
    """Return True if the file has a Keys:CreationDate tag set."""
    try:
        result = subprocess.run(
            ["exiftool", "-s3", "-Keys:CreationDate", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        val = result.stdout.strip()
        return bool(val and val != "-")
    except Exception:
        return False


class TimeShiftError(Exception):
    """Raised when time shift parsing or application fails."""

    pass


def parse_shift(shift_str: str) -> timedelta:
    """Parse time shift string to timedelta.

    Format: [+|-][DD:]HH:MM:SS
    Examples:
        "+08:00:00" → +8 hours
        "-00:30:00" → -30 minutes
        "+1:12:00:00" → +1 day, +12 hours
        "-1:12:30:00" → -1 day, -12 hours, -30 minutes

    Args:
        shift_str: Time shift string with optional +/- prefix

    Returns:
        Signed timedelta

    Raises:
        TimeShiftError: If format is invalid
    """
    if not shift_str:
        raise TimeShiftError("Shift string is empty")

    # Strip leading +/-, remember sign
    is_negative = shift_str.startswith("-")
    shift_str = shift_str.lstrip("+-")

    # Split on colon
    parts = shift_str.split(":")
    if len(parts) == 3:
        # HH:MM:SS
        try:
            hours, minutes, seconds = map(int, parts)
            days = 0
        except ValueError as e:
            raise TimeShiftError(f"Invalid shift format (HH:MM:SS): {shift_str}") from e
    elif len(parts) == 4:
        # DD:HH:MM:SS
        try:
            days, hours, minutes, seconds = map(int, parts)
        except ValueError as e:
            raise TimeShiftError(f"Invalid shift format (DD:HH:MM:SS): {shift_str}") from e
    else:
        raise TimeShiftError(
            f"Invalid shift format. Expected [+|-][DD:]HH:MM:SS, got: {shift_str}"
        )

    # Validate ranges
    if not (0 <= hours < 24):
        raise TimeShiftError(f"Hours must be 0-23, got {hours}")
    if not (0 <= minutes < 60):
        raise TimeShiftError(f"Minutes must be 0-59, got {minutes}")
    if not (0 <= seconds < 60):
        raise TimeShiftError(f"Seconds must be 0-59, got {seconds}")

    result = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    if is_negative:
        result = -result
    return result


def format_exiftool_shift(td: timedelta) -> tuple[str, str]:
    """Format timedelta to exiftool shift syntax.

    Returns:
        Tuple of (operator, shift_str) where operator is "+=" or "-="
        and shift_str is in exiftool format "0:0:D H:M:S"

    Example:
        timedelta(hours=8) → ("+=", "0:0:0 8:0:0")
        timedelta(hours=-8) → ("-=", "0:0:0 8:0:0")
    """
    # Get absolute values
    total_seconds = abs(int(td.total_seconds()))
    days = total_seconds // 86400
    remaining = total_seconds % 86400
    hours = remaining // 3600
    remaining = remaining % 3600
    minutes = remaining // 60
    seconds = remaining % 60

    operator = "-=" if td.total_seconds() < 0 else "+="
    shift_str = f"0:0:{days} {hours}:{minutes}:{seconds}"

    return operator, shift_str


def write_time_shift(
    file_path: str | Path,
    shift_td: timedelta,
    backup: bool = False,
    dry_run: bool = False,
    timeout: int = 60,
) -> bool:
    """Apply datetime shift to image or video file via exiftool.

    Shifts DateTimeOriginal and CreateDate (images) or QuickTime tags (videos)
    by the specified timedelta.

    Args:
        file_path: Path to image or video file
        shift_td: Signed timedelta to shift by
        backup: If True, keep _original backup file; default overwrites
        dry_run: If True, don't actually write, just log what would happen
        timeout: exiftool subprocess timeout in seconds

    Returns:
        True if write succeeded or dry_run=True, False if write failed
    """
    file_path = Path(file_path)
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return False

    # Clean up stale exiftool temporary files that may block writes
    temp_file = Path(str(file_path) + "_exiftool_tmp")
    if temp_file.exists():
        try:
            temp_file.unlink()
            logger.debug(f"Cleaned up stale temp file: {temp_file.name}")
        except Exception as e:
            logger.warning(f"Could not remove temp file {temp_file.name}: {e}")

    # Format shift for exiftool
    operator, shift_str = format_exiftool_shift(shift_td)

    # Determine file type
    is_video = file_path.suffix.lower() in [".mp4", ".mov", ".m4v"]

    # Build exiftool command
    cmd = ["exiftool", "-api", "ignoreMinorErrors=1"]

    if is_video:
        # For videos: shift QuickTime tags and XMP tags for Windows player compatibility
        cmd.extend([
            f"-QuickTime:CreateDate{operator}\"{shift_str}\"",
            f"-QuickTime:MediaCreateDate{operator}\"{shift_str}\"",
            # Also shift XMP tags for Windows player compatibility
            f"-XMP-exif:DateTimeOriginal{operator}\"{shift_str}\"",
            f"-XMP:CreateDate{operator}\"{shift_str}\"",
        ])
        # Also shift Keys:CreationDate if present (written by location tagger or Apple devices).
        # This timezone-aware field is prioritised by Immich (CreationDate, rank 4) over the
        # naive QuickTime:CreateDate (rank 5). Keeping it in sync prevents the double-shift
        # where Immich would otherwise re-apply GPS timezone on top of the shifted UTC value.
        if _has_keys_creation_date(file_path):
            cmd.append(f"-Keys:CreationDate{operator}\"{shift_str}\"")
    else:
        # For images and raw: shift EXIF tags
        cmd.extend([
            f"-DateTimeOriginal{operator}\"{shift_str}\"",
            f"-CreateDate{operator}\"{shift_str}\"",
        ])

    # Backup/overwrite mode
    if not backup:
        cmd.append("-overwrite_original")

    # Add file path at the end
    cmd.append(str(file_path))

    if dry_run:
        logger.info(f"[DRY RUN] Would write: {' '.join(cmd)}")
        return True

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode == 0:
            shift_display = f"{operator[0]}{shift_str.replace(' ', ':')}"
            logger.info(f"[OK] {file_path.name}: shifted by {shift_display}")
            return True
        else:
            logger.error(f"exiftool write failed for {file_path.name}: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"exiftool timed out shifting {file_path.name}")
        return False
    except Exception as e:
        logger.error(f"Error shifting {file_path.name}: {e}")
        return False
