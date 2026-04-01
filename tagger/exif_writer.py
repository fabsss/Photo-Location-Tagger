"""Read and write EXIF/metadata to images and videos via exiftool subprocess."""

import json
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


def read_datetime_batch(
    file_paths: list[Path],
    chunk_size: int = 200,
) -> dict[Path, datetime | None]:
    """Read image/video creation timestamps from multiple files via batch exiftool.

    Splits file_paths into chunks to stay under Windows command-line length limit (~32,767 chars).
    Per chunk: runs `exiftool -json -DateTimeOriginal -CreateDate -f file1 file2 ...`
    Parses JSON response and extracts DateTimeOriginal/CreateDate for each file.

    Args:
        file_paths: List of Path objects to read timestamps from
        chunk_size: Max files per exiftool invocation (default 200)

    Returns:
        dict[Path, datetime | None] — timestamp for each file (None if not found/error)

    Example:
        paths = [Path("photo1.jpg"), Path("photo2.jpg")]
        timestamps = read_datetime_batch(paths)
        for path, dt in timestamps.items():
            print(f"{path.name}: {dt}")
    """
    result_map = {}

    if not file_paths:
        return result_map

    # Split into chunks by count first
    chunks = []
    for i in range(0, len(file_paths), chunk_size):
        chunks.append(file_paths[i : i + chunk_size])

    # For chunks with very long paths, sub-chunk by character count
    final_chunks = []
    for chunk in chunks:
        accumulated_length = 0
        sub_chunk = []
        for file_path in chunk:
            file_str = str(file_path)
            accumulated_length += len(file_str) + 1  # +1 for space between args
            if accumulated_length > 30000:  # Conservative limit (Windows is ~32,767)
                if sub_chunk:
                    final_chunks.append(sub_chunk)
                sub_chunk = [file_path]
                accumulated_length = len(file_str) + 1
            else:
                sub_chunk.append(file_path)
        if sub_chunk:
            final_chunks.append(sub_chunk)

    # Process each chunk
    for chunk in final_chunks:
        try:
            # Read both EXIF (for images) and QuickTime (for videos) date tags
            # exiftool will return "-" for tags that don't exist in the file
            cmd = [
                "exiftool", "-json",
                "-DateTimeOriginal", "-CreateDate",  # EXIF tags for images
                "-QuickTime:CreateDate", "-QuickTime:MediaCreateDate",  # QuickTime tags for videos
                "-f"
            ]
            cmd.extend(str(fp) for fp in chunk)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.warning(f"exiftool batch read failed: {result.stderr}")
                # Mark all files in chunk as failed
                for fp in chunk:
                    result_map[fp] = None
                continue

            # Parse JSON array
            try:
                json_data = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse exiftool JSON output: {e}")
                for fp in chunk:
                    result_map[fp] = None
                continue

            if not isinstance(json_data, list):
                json_data = [json_data]

            # Map results by SourceFile path
            for entry in json_data:
                if not isinstance(entry, dict):
                    continue

                try:
                    source_file = entry.get("SourceFile")
                    if not source_file:
                        continue

                    source_path = Path(source_file)

                    # Try EXIF tags first (for images), then QuickTime tags (for videos)
                    # Note: exiftool returns "-" for missing tags, so we must check for it
                    datetime_str = None
                    for tag in ["DateTimeOriginal", "CreateDate", "QuickTime:CreateDate", "QuickTime:MediaCreateDate"]:
                        val = entry.get(tag)
                        if val and val != "-":
                            datetime_str = val
                            break

                    if not datetime_str:
                        result_map[source_path] = None
                        continue

                    # Convert exiftool format "YYYY:MM:DD HH:MM:SS" to ISO
                    exif_datetime_str = datetime_str.replace(":", "-", 2)
                    try:
                        result_map[source_path] = datetime.fromisoformat(exif_datetime_str)
                    except ValueError:
                        logger.debug(f"Could not parse datetime for {source_file}: {datetime_str}")
                        result_map[source_path] = None

                except (KeyError, TypeError) as e:
                    logger.debug(f"Error processing JSON entry: {e}")
                    continue

        except subprocess.TimeoutExpired:
            logger.warning(f"exiftool batch read timed out for chunk of {len(chunk)} files")
            for fp in chunk:
                result_map[fp] = None
        except Exception as e:
            logger.error(f"Unexpected error in batch read: {e}")
            for fp in chunk:
                result_map[fp] = None

    return result_map


def read_datetime(file_path: str | Path) -> datetime | None:
    """Read image/video creation timestamp from metadata.

    For images (JPG, PNG, etc): reads EXIF DateTimeOriginal, then CreateDate
    For videos (MP4, MOV): reads QuickTime tags CreateDate, MediaCreateDate
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
        # Determine which tags to read based on file type
        is_video = file_path.suffix.lower() in [".mp4", ".mov", ".m4v"]

        if is_video:
            # For videos: read QuickTime tags (CreateDate, MediaCreateDate, etc.)
            # These tags are in QuickTime format, not EXIF
            tags_to_read = [
                "-QuickTime:CreateDate",
                "-QuickTime:MediaCreateDate",
                "-CreateDate",  # Fallback to any CreateDate
            ]
        else:
            # For images: read EXIF tags
            tags_to_read = ["-DateTimeOriginal", "-CreateDate"]

        # exiftool -s3 outputs tag values only (no field names)
        # exiftool -f outputs data in the same format exiftool uses
        cmd = ["exiftool"] + tags_to_read + ["-s3", "-f", str(file_path)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
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

        tag_type = "QuickTime" if is_video else "EXIF"
        logger.warning(f"No {tag_type} timestamp found in {file_path.name}")
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
    cmd = ["exiftool", "-api", "ignoreMinorErrors=1"]

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
            timeout=60,
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
