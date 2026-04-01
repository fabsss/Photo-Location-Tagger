#!/usr/bin/env python3
"""CLI: Geotag photos and videos using Google Location History timeline.json."""

import argparse
import logging
import sys
from pathlib import Path

from tagger.timeline_parser import load_timeline, TimelineParseError
from tagger.location_finder import find_closest
from tagger.exif_writer import check_exiftool, read_datetime, write_location, ExifToolNotFoundError


# Setup logging
def setup_logging(log_file: Path | None = None, verbose: bool = False):
    """Configure logging with console + optional file output."""
    log_format = "[%(levelname)-8s] %(asctime)s | %(name)s | %(message)s"
    date_format = "%H:%M:%S"

    # Console handler (INFO or DEBUG)
    console_handler = logging.StreamHandler(sys.stdout)
    console_level = logging.DEBUG if verbose else logging.INFO
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all, handlers filter
    root_logger.addHandler(console_handler)

    # File handler (DEBUG if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
        root_logger.addHandler(file_handler)
        console_handler.setFormatter(
            logging.Formatter("%(message)s")
        )  # Simplify console format when file logging

    return root_logger


logger = logging.getLogger(__name__)


def process_directory(
    timeline_points,
    input_dir: Path,
    time_margin: int,
    dry_run: bool,
    backup: bool,
    recursive: bool,
    extensions: list[str],
) -> tuple[int, int, int]:
    """Process all matching files in a directory.

    Args:
        timeline_points: List of GPSPoint objects from timeline.json
        input_dir: Directory to process
        time_margin: Max time difference in minutes
        dry_run: Don't write if True
        backup: Keep _original backups if True
        recursive: Process subdirectories if True
        extensions: File extensions to process (lowercase, without dot)

    Returns:
        (tagged_count, skipped_count, failed_count)
    """
    tagged = 0
    skipped = 0
    failed = 0

    # Find all matching files
    pattern = "**/*" if recursive else "*"
    files_to_process = []

    for ext in extensions:
        for file_path in input_dir.glob(f"{pattern}"):
            if file_path.is_file() and file_path.suffix.lower().lstrip(".") == ext:
                files_to_process.append(file_path)

    if not files_to_process:
        logger.warning(f"No matching files found in {input_dir}")
        return 0, 0, 0

    logger.info(f"Found {len(files_to_process)} file(s) to process")

    for file_path in sorted(files_to_process):
        # Read image timestamp
        image_dt = read_datetime(file_path)
        if image_dt is None:
            logger.warning(f"{file_path.name}: No readable timestamp found")
            skipped += 1
            continue

        # Find closest GPS point
        point = find_closest(image_dt, timeline_points, max_delta_minutes=time_margin)
        if point is None:
            logger.warning(f"{file_path.name}: No GPS match within {time_margin} min")
            skipped += 1
            continue

        # Write location
        success = write_location(file_path, point, backup=backup, dry_run=dry_run)
        if success:
            tagged += 1
        else:
            failed += 1

    return tagged, skipped, failed


def prompt_for_path(prompt_text: str, must_exist: bool = True) -> Path:
    """Interactively prompt user for a file or directory path."""
    while True:
        path_str = input(f"{prompt_text}: ").strip()
        if not path_str:
            print("Error: Path cannot be empty")
            continue

        path = Path(path_str).expanduser()
        if must_exist and not path.exists():
            print(f"Error: Path does not exist: {path}")
            continue

        return path


def prompt_for_interactive_mode() -> dict:
    """Interactively prompt user for all configuration options."""
    print("\n" + "="*60)
    print("Photo-Location-Tagger - Interactive Mode")
    print("="*60 + "\n")

    # Timeline file
    print("Step 1: Locate your Google Timeline file")
    print("  Export Location History from Google Maps on your device")
    print("  (See README for detailed instructions)\n")
    timeline = prompt_for_path("Enter path to timeline.json", must_exist=True)

    # Input file/folder
    print("\nStep 2: Select photos/videos to geotag")
    input_path = prompt_for_path("Enter path to photo/folder", must_exist=True)

    # Time margin
    print("\nStep 3: Configure matching (optional, press Enter for defaults)")
    while True:
        margin_str = input("Max time difference in minutes (default: 30): ").strip()
        if not margin_str:
            time_margin = 30
            break
        try:
            time_margin = int(margin_str)
            if time_margin <= 0:
                print("Error: Must be a positive number")
                continue
            break
        except ValueError:
            print("Error: Must be a number")

    # File extensions
    print("\nSupported formats:")
    print("  Images: jpg, jpeg, png, tiff, tif, webp")
    print("  Raw (DNG): dng")
    print("  Raw (Sony): arw, srf, sr2")
    print("  Raw (Canon): cr2, cr3, crw")
    print("  Raw (Nikon): nef, nrw")
    print("  Raw (Fujifilm): raf")
    print("  Raw (Panasonic): rw2, rwl")
    print("  Raw (Olympus): orf")
    print("  Raw (Pentax): pef, ptx")
    print("  Raw (Epson): erf")
    print("  Raw (Samsung): srw")
    print("  Raw (GoPro): gpr")
    print("  Raw (Hasselblad): 3fr")
    print("  Video: mp4, mov\n")
    ext_str = input("File extensions to process (default: all of above): ").strip()
    extensions = ext_str if ext_str else "jpg,jpeg,png,tiff,tif,webp,dng,arw,srf,sr2,cr2,cr3,crw,nef,nrw,raf,rw2,rwl,orf,pef,ptx,erf,srw,gpr,3fr,mp4,mov"

    # Optional settings
    print("\nStep 4: Additional options (y/n)")
    recursive = input("Process subfolders recursively? (y/n, default: n): ").strip().lower() == "y"
    backup = input("Keep backup files? (y/n, default: n): ").strip().lower() == "y"
    dry_run = input("Dry run (preview only, no changes)? (y/n, default: n): ").strip().lower() == "y"

    log_file_str = input("Save detailed log to file? (enter path or press Enter to skip): ").strip()
    log_file = Path(log_file_str) if log_file_str else None

    verbose = input("Enable verbose logging? (y/n, default: n): ").strip().lower() == "y"

    print("\n" + "="*60 + "\n")

    return {
        "timeline": timeline,
        "input": input_path,
        "time_margin": time_margin,
        "extensions": extensions,
        "recursive": recursive,
        "backup": backup,
        "dry_run": dry_run,
        "log_file": log_file,
        "verbose": verbose,
    }


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Geotag photos and videos using Google Location History (timeline.json)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run interactively (guided prompts)
  python tagger_cli.py

  # Process single photo
  python tagger_cli.py --timeline timeline.json --input photo.jpg

  # Process all JPEGs in a folder
  python tagger_cli.py --timeline timeline.json --input ./photos --extensions jpg,jpeg

  # Process with 60-minute time margin and save log
  python tagger_cli.py --timeline timeline.json --input ./trip --time-margin 60 --log-file tagger.log

  # Dry run to see what would be tagged
  python tagger_cli.py --timeline timeline.json --input ./photos --dry-run
        """,
    )

    parser.add_argument(
        "--timeline",
        required=False,
        type=Path,
        help="Path to Google Timeline JSON file",
    )
    parser.add_argument(
        "--input",
        required=False,
        type=Path,
        help="File or folder to process",
    )
    parser.add_argument(
        "--time-margin",
        type=int,
        default=30,
        help="Max time difference between image and GPS point in minutes (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be tagged without writing",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Write detailed log to file",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Keep _original backup files (default: overwrite)",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Process subfolders recursively",
    )
    parser.add_argument(
        "--extensions",
        type=str,
        default="jpg,jpeg,png,tiff,tif,webp,dng,arw,srf,sr2,cr2,cr3,crw,nef,nrw,raf,rw2,rwl,orf,pef,ptx,erf,srw,gpr,3fr,mp4,mov",
        help="Comma-separated file extensions to process (default: all common image and video formats)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging (DEBUG level)",
    )

    args = parser.parse_args()

    # Check if running in interactive mode (no required args provided)
    if args.timeline is None or args.input is None:
        try:
            # Prompt user for configuration
            config = prompt_for_interactive_mode()
            # Convert to args-like object
            args.timeline = config["timeline"]
            args.input = config["input"]
            args.time_margin = config["time_margin"]
            args.extensions = config["extensions"]
            args.recursive = config["recursive"]
            args.backup = config["backup"]
            args.dry_run = config["dry_run"]
            args.log_file = config["log_file"]
            args.verbose = config["verbose"]
        except KeyboardInterrupt:
            print("\nCancelled by user")
            return 1

    # Setup logging
    setup_logging(log_file=args.log_file, verbose=args.verbose)

    try:
        # Verify exiftool
        logger.info("Checking for exiftool...")
        check_exiftool()

        # Load timeline
        logger.info(f"Loading timeline from {args.timeline.name}...")
        timeline_points = load_timeline(args.timeline)

        # Parse extensions
        extensions = [ext.strip().lstrip(".").lower() for ext in args.extensions.split(",")]

        # Process input
        logger.info(f"Processing {args.input.name}...")
        if args.input.is_file():
            # Single file
            image_dt = read_datetime(args.input)
            if image_dt is None:
                logger.error(f"No readable timestamp in {args.input.name}")
                return 1

            point = find_closest(image_dt, timeline_points, max_delta_minutes=args.time_margin)
            if point is None:
                logger.error(f"No GPS match for {args.input.name}")
                return 1

            success = write_location(
                args.input,
                point,
                backup=args.backup,
                dry_run=args.dry_run,
            )
            return 0 if success else 1

        elif args.input.is_dir():
            # Directory
            tagged, skipped, failed = process_directory(
                timeline_points,
                args.input,
                time_margin=args.time_margin,
                dry_run=args.dry_run,
                backup=args.backup,
                recursive=args.recursive,
                extensions=extensions,
            )

            logger.info("=" * 60)
            if args.dry_run:
                logger.info(f"DRY RUN SUMMARY: {tagged} would be tagged, {skipped} skipped")
            else:
                logger.info(
                    f"SUMMARY: {tagged} tagged, {skipped} skipped, {failed} failed"
                )
            logger.info("=" * 60)

            return 0 if (failed == 0 and tagged > 0) else (1 if failed > 0 else 0)

        else:
            logger.error(f"{args.input} is neither a file nor a directory")
            return 1

    except ExifToolNotFoundError as e:
        logger.error(str(e))
        return 1
    except TimelineParseError as e:
        logger.error(str(e))
        return 1
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=args.verbose)
        return 1


if __name__ == "__main__":
    sys.exit(main())
