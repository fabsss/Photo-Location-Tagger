"""Read and write EXIF/metadata to images and videos via exiftool subprocess."""

import logging
import subprocess
from datetime import datetime
from pathlib import Path

from .timeline_parser import GPSPoint


logger = logging.getLogger(__name__)


class ExifToolNotFoundError(Exception):
    """Raised when exiftool is not installed or not on PATH."""

    pass


def check_exiftool() -> bool:
    """Verify exiftool is installed and accessible.

    Returns:
        True if exiftool is available

    Raises:
        ExifToolNotFoundError: If exiftool is not found
    """
    try:
        result = subprocess.run(
            ["exiftool", "-ver"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            logger.debug(f"exiftool found: {version}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    raise ExifToolNotFoundError(
        "exiftool not found. Install it with:\n"
        "  Windows (chocolatey): choco install exiftool\n"
        "  macOS (homebrew): brew install exiftool\n"
        "  Linux: sudo apt-get install libimage-exiftool-perl"
    )


def read_datetime(file_path: str | Path) -> datetime | None:
    """Read image/video creation timestamp from EXIF metadata.

    Tries DateTimeOriginal (images) first, then CreateDate (videos).
    Format is "YYYY:MM:DD HH:MM:SS" (naive datetime, assumes local time).

    Args:
        file_path: Path to image or video file

    Returns:
        Naive datetime object, or None if no timestamp found

    Raises:
        subprocess.CalledProcessError: If exiftool subprocess fails unexpectedly
    """
    file_path = Path(file_path)
    if not file_path.exists():
        logger.warning(f"File not found: {file_path}")
        return None

    try:
        # exiftool -s3 outputs tag values only (no field names)
        # exiftool -f outputs data in the same format exiftool uses
        result = subprocess.run(
            ["exiftool", "-DateTimeOriginal", "-CreateDate", "-s3", "-f", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            logger.warning(f"exiftool read failed for {file_path.name}: {result.stderr}")
            return None

        # Output format: "YYYY:MM:DD HH:MM:SS" or "-" if tag not present
        lines = result.stdout.strip().split("\n")
        for line in lines:
            if line and line != "-":
                # Convert exiftool format "YYYY:MM:DD HH:MM:SS" to ISO "YYYY-MM-DD HH:MM:SS"
                exif_datetime_str = line.replace(":", "-", 2)  # Replace first 2 colons
                try:
                    return datetime.fromisoformat(exif_datetime_str)
                except ValueError:
                    logger.debug(f"Could not parse datetime: {line}")
                    continue

        logger.warning(f"No DateTimeOriginal or CreateDate found in {file_path.name}")
        return None

    except subprocess.TimeoutExpired:
        logger.error(f"exiftool timed out reading {file_path.name}")
        return None
    except Exception as e:
        logger.error(f"Error reading datetime from {file_path.name}: {e}")
        return None


def write_location(
    file_path: str | Path,
    point: GPSPoint,
    backup: bool = False,
    dry_run: bool = False,
) -> bool:
    """Write GPS coordinates and timezone offset to image/video EXIF metadata.

    Writes:
    - GPSLatitude, GPSLongitude, GPSLatitudeRef, GPSLongitudeRef (all formats)
    - OffsetTimeOriginal (images, EXIF format)
    - Keys:GPSCoordinates (MP4 videos)

    Args:
        file_path: Path to image or video file
        point: GPSPoint with location and timezone data
        backup: If True, keep _original backup file; default overwrites
        dry_run: If True, don't actually write, just log what would happen

    Returns:
        True if write succeeded or dry_run=True, False if write failed

    Example:
        point = GPSPoint(..., lat=52.5, lon=13.3, tz_offset_str="+01:00")
        if write_location("photo.jpg", point):
            print("Photo geotagged!")
    """
    file_path = Path(file_path)
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return False

    # Build exiftool command
    cmd = ["exiftool"]

    # GPS coordinates
    lat_ref = "N" if point.lat >= 0 else "S"
    lon_ref = "E" if point.lon >= 0 else "W"
    cmd.extend([
        f"-GPSLatitude={abs(point.lat)}",
        f"-GPSLongitude={abs(point.lon)}",
        f"-GPSLatitudeRef={lat_ref}",
        f"-GPSLongitudeRef={lon_ref}",
    ])

    # Timezone offset (for images and raw formats)
    # Includes: JPEG, PNG, TIFF, WebP, and raw formats from major camera brands
    image_formats = [
        ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp",
        # Adobe raw
        ".dng",
        # Sony
        ".arw", ".srf", ".sr2",
        # Canon
        ".cr2", ".cr3", ".crw",
        # Nikon
        ".nef", ".nrw",
        # Fujifilm
        ".raf",
        # Panasonic/Lumix
        ".rw2", ".rwl",
        # Olympus
        ".orf",
        # Pentax
        ".pef", ".ptx", ".dng",
        # Epson
        ".erf",
        # Samsung
        ".srw",
        # GoPro
        ".gpr",
        # Leica
        ".dng", ".rwl",
        # Hasselblad
        ".3fr",
    ]
    if file_path.suffix.lower() in image_formats:
        cmd.append(f"-OffsetTimeOriginal={point.tz_offset_str}")

    # Timezone offset (for MP4 videos)
    if file_path.suffix.lower() in [".mp4", ".mov"]:
        # MP4 uses a different tag structure
        cmd.append(f"-Keys:GPSCoordinates={point.lat},{point.lon}")

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
            timeout=15,
        )

        if result.returncode == 0:
            logger.info(
                f"✓ {file_path.name}: {point.lat:.4f}, {point.lon:.4f} ({point.tz_offset_str})"
            )
            return True
        else:
            logger.error(f"exiftool write failed for {file_path.name}: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"exiftool timed out writing {file_path.name}")
        return False
    except Exception as e:
        logger.error(f"Error writing to {file_path.name}: {e}")
        return False
