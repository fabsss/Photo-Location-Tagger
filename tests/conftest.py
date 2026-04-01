"""Pytest configuration and fixtures."""

import subprocess
from pathlib import Path

import pytest
from PIL import Image
import piexif


@pytest.fixture(scope="session", autouse=True)
def create_test_image():
    """Create a minimal test JPEG with DateTimeOriginal EXIF tag."""
    fixture_dir = Path(__file__).parent / "fixtures"
    fixture_dir.mkdir(exist_ok=True)

    jpg_path = fixture_dir / "sample.jpg"

    # Create 1x1 pixel JPEG
    img = Image.new("RGB", (1, 1), color=(255, 0, 0))

    # Create EXIF with DateTimeOriginal = "2025:12:13 00:02:00" (matches sample_timeline.json)
    exif_ifd = {
        piexif.ExifIFD.DateTimeOriginal: b"2025:12:13 00:02:00",
    }
    exif_dict = {
        "0th": {},
        "Exif": exif_ifd,
        "GPS": {},
        "1st": {},
        "Interop": {},
    }
    exif_bytes = piexif.dump(exif_dict)

    img.save(jpg_path, "jpeg", exif=exif_bytes)
    print(f"Created test image: {jpg_path}")


@pytest.fixture(scope="session", autouse=True)
def create_test_video():
    """Create a minimal test MP4 with CreateDate metadata."""
    fixture_dir = Path(__file__).parent / "fixtures"
    fixture_dir.mkdir(exist_ok=True)

    mp4_path = fixture_dir / "sample.mp4"

    # Only create if ffmpeg is available
    try:
        # Create a minimal 1-frame H.264 video using ffmpeg
        # This requires ffmpeg to be installed
        result = subprocess.run(
            [
                "ffmpeg",
                "-f", "lavfi",
                "-i", "color=c=red:s=1x1:d=0.1",  # 1x1 red frame, 0.1 second duration
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-y",  # Overwrite
                str(mp4_path),
            ],
            capture_output=True,
            timeout=15,
        )

        if result.returncode == 0:
            # Add CreateDate metadata using exiftool
            subprocess.run(
                [
                    "exiftool",
                    "-CreateDate=2025:12:13 00:02:00",
                    "-overwrite_original",
                    str(mp4_path),
                ],
                capture_output=True,
                timeout=10,
            )
            print(f"Created test video: {mp4_path}")
        else:
            print(f"Warning: Could not create test MP4 (ffmpeg failed or not installed)")

    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("Warning: ffmpeg not available, skipping MP4 creation")
