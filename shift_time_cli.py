#!/usr/bin/env python3
"""CLI: Shift datetime of photos and videos by a specified offset."""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from datetime import datetime, timedelta
from pathlib import Path

from tagger.exif_writer import check_exiftool, read_datetime, ExifToolNotFoundError
from tagger.time_shifter import parse_shift, write_time_shift, TimeShiftError


logger = logging.getLogger(__name__)


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
        # Log where the output is being written
        root_logger.info(f"Logging to: {log_file}")

    return root_logger


def get_unique_log_path(log_file: Path) -> Path:
    """Get a unique log file path by appending counter if file exists.

    If log_file already exists, returns log_file.1, log_file.2, etc.

    Args:
        log_file: Desired log file path

    Returns:
        Unique log file path that doesn't exist yet

    Example:
        get_unique_log_path(Path("tagger.log"))
        # Returns Path("tagger.log") if it doesn't exist
        # Returns Path("tagger.log.1") if tagger.log exists
        # Returns Path("tagger.log.2") if tagger.log and tagger.log.1 exist
    """
    if not log_file.exists():
        return log_file

    counter = 1
    while True:
        unique_path = Path(f"{log_file}.{counter}")
        if not unique_path.exists():
            return unique_path
        counter += 1


def prompt_for_path(prompt_text: str, must_exist: bool = True, path_type: str = "any") -> Path:
    """Interactively prompt user for a file or directory path.

    Args:
        prompt_text: Text to display in the prompt
        must_exist: Whether the path must exist
        path_type: "file", "directory", or "any"
    """
    while True:
        path_str = input(f"{prompt_text}: ").strip()
        if not path_str:
            print("Error: Path cannot be empty")
            continue

        path = Path(path_str).expanduser()

        if must_exist and not path.exists():
            print(f"Error: Path does not exist: {path}")
            continue

        # Validate path type
        if path_type == "file":
            if path.exists() and path.is_dir():
                print(f"Error: '{path_str}' is a directory, not a file.")
                print(f"  Please enter a file path (e.g., 'photo.jpg')")
                continue
        elif path_type == "directory":
            if path.exists() and path.is_file():
                print(f"Error: '{path_str}' is a file, not a directory.")
                print(f"  Please enter a folder path (e.g., './photos' or '.')")
                continue

        return path


def process_directory(
    input_dir: Path,
    shift_td: timedelta,
    dry_run: bool,
    backup: bool,
    recursive: bool,
    extensions: list[str],
    workers: int = 4,
    timeout: int = 60,
) -> tuple[int, int, int]:
    """Process all matching files in a directory.

    Args:
        input_dir: Directory to process
        shift_td: Signed timedelta to shift by
        dry_run: Don't write if True
        backup: Keep _original backups if True
        recursive: Process subdirectories if True
        extensions: File extensions to process (lowercase, without dot)
        workers: Number of parallel workers (default 4). If 1, uses sequential mode.
        timeout: exiftool subprocess timeout in seconds

    Returns:
        (shifted_count, skipped_count, failed_count)
    """
    shifted = 0
    skipped = 0
    failed = 0

    # Find all matching files with improved glob for case-sensitive OSes
    pattern = "**/*" if recursive else "*"
    files_to_process = []
    seen = set()

    for ext in extensions:
        # Glob both lowercase and uppercase variants (for Linux case-sensitive filesystems)
        for variant in (ext.lower(), ext.upper()):
            for file_path in input_dir.glob(f"{pattern}.{variant}"):
                if file_path.is_file() and file_path not in seen:
                    seen.add(file_path)
                    files_to_process.append(file_path)

    if not files_to_process:
        logger.warning(f"No matching files found in {input_dir}")
        return 0, 0, 0

    logger.info(f"Found {len(files_to_process)} file(s) to process")

    files_to_process_sorted = sorted(files_to_process)

    # Process files (parallel or sequential)
    if workers > 1:
        # Parallel execution with ThreadPoolExecutor
        def _process_one(file_path):
            success = write_time_shift(
                file_path,
                shift_td,
                backup=backup,
                dry_run=dry_run,
                timeout=timeout,
            )
            return "shifted" if success else "failed"

        results = []
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_process_one, fp): fp for fp in files_to_process_sorted}
                try:
                    for future in as_completed(futures):
                        results.append(future.result())
                except KeyboardInterrupt:
                    logger.warning(f"Processing interrupted by user. Giving running tasks {timeout}s to complete...")
                    # Wait for running tasks with timeout (don't hang forever)
                    wait(futures.keys(), timeout=timeout)
                    pool.shutdown(wait=False)  # Shutdown without waiting again
                    raise  # Re-raise to exit main loop
        except KeyboardInterrupt:
            # Count partial results before exiting
            pass

        shifted = results.count("shifted")
        failed = results.count("failed")
        skipped = len(files_to_process) - shifted - failed

    else:
        # Sequential execution
        try:
            for file_path in files_to_process_sorted:
                success = write_time_shift(
                    file_path,
                    shift_td,
                    backup=backup,
                    dry_run=dry_run,
                    timeout=timeout,
                )
                if success:
                    shifted += 1
                else:
                    failed += 1
        except KeyboardInterrupt:
            logger.warning("Processing interrupted by user")
            raise  # Re-raise to exit main loop

    return shifted, skipped, failed


def prompt_for_interactive_mode() -> dict:
    """Interactively prompt user for all configuration options."""
    print("\n" + "="*60)
    print("Time Shift - Shift photo/video timestamps")
    print("="*60 + "\n")

    # Input folder
    print("Step 1: Select photos/videos to shift")
    input_path = prompt_for_path("Enter path to photo/folder", must_exist=True, path_type="directory")

    # Discover files and show first file info
    print("\nStep 2: Preview first file")
    pattern = "*"
    extensions_default = [
        "jpg", "jpeg", "png", "tiff", "tif", "webp",
        "dng", "arw", "srf", "sr2", "cr2", "cr3", "crw",
        "nef", "nrw", "raf", "rw2", "rwl", "orf", "pef", "ptx",
        "erf", "srw", "gpr", "3fr", "mp4", "mov"
    ]

    files_found = []
    seen = set()
    for ext in extensions_default:
        for variant in (ext.lower(), ext.upper()):
            for file_path in input_path.glob(f"{pattern}.{variant}"):
                if file_path.is_file() and file_path not in seen:
                    seen.add(file_path)
                    files_found.append(file_path)

    if not files_found:
        print(f"Error: No supported files found in {input_path}")
        print("  Supported formats: JPG, PNG, DNG, and other raw/video formats")
        sys.exit(1)

    files_found_sorted = sorted(files_found)
    first_file = files_found_sorted[0]
    first_dt = read_datetime(first_file)

    if first_dt is None:
        print(f"Error: Could not read timestamp from {first_file.name}")
        sys.exit(1)

    print(f"  First file: {first_file.name}")
    print(f"  Current time: {first_dt.strftime('%Y:%m:%d %H:%M:%S')}")
    print(f"  Total files found: {len(files_found)}\n")

    # Get shift value
    print("Step 3: Enter time shift")
    print("  Format: [+|-][DD:]HH:MM:SS")
    print("  Examples: +08:00:00, -00:30:00, +1:12:00:00\n")
    while True:
        shift_str = input("Enter time shift: ").strip()
        if not shift_str:
            print("Error: Shift cannot be empty")
            continue
        try:
            shift_td = parse_shift(shift_str)
            break
        except TimeShiftError as e:
            print(f"Error: {e}")

    # Show preview
    new_dt = first_dt + shift_td
    print("\nStep 4: Preview")
    print(f"  Original: {first_dt.strftime('%Y:%m:%d %H:%M:%S')}")
    print(f"  Shift:    {shift_str}")
    print(f"  Result:   {new_dt.strftime('%Y:%m:%d %H:%M:%S')}")

    # Confirm
    confirm = input("\nApply this shift to all files? (y/n, default: y): ").strip().lower()
    if confirm == "n":
        print("Cancelled by user")
        sys.exit(0)

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
    print("\nStep 5: Additional options (y/n)")
    recursive = input("Process subfolders recursively? (y/n, default: n): ").strip().lower() == "y"
    backup = input("Keep backup files? (y/n, default: n): ").strip().lower() == "y"
    dry_run = input("Dry run (preview only, no changes)? (y/n, default: n): ").strip().lower() == "y"

    # Log file with validation
    log_file = None
    while True:
        log_file_str = input("Save detailed log to file? (e.g., shift.log or ./logs/shift.log, or press Enter to skip): ").strip()
        if not log_file_str:
            # User skipped
            break

        log_path = Path(log_file_str).expanduser()

        # Check if it's a directory
        if log_path.is_dir():
            print(f"Error: '{log_file_str}' is a directory. Please provide a filename instead.")
            print("  Example filenames: 'shift.log', './logs/shift.log', 'C:\\Users\\YourName\\shift.log'")
            continue

        # Check if parent directory exists
        if not log_path.parent.exists():
            print(f"Error: Directory does not exist: {log_path.parent}")
            continue

        log_file = log_path
        break

    verbose = input("Enable verbose logging? (y/n, default: n): ").strip().lower() == "y"

    # Workers for parallel processing
    while True:
        workers_str = input("Number of parallel workers (default: 4, use 1 for sequential): ").strip()
        if not workers_str:
            workers = 4
            break
        try:
            workers = int(workers_str)
            if workers < 1:
                print("Error: Must be at least 1")
                continue
            break
        except ValueError:
            print("Error: Must be a number")

    print("\n" + "="*60 + "\n")

    return {
        "input": input_path,
        "shift": shift_td,
        "extensions": extensions,
        "recursive": recursive,
        "backup": backup,
        "dry_run": dry_run,
        "log_file": log_file,
        "verbose": verbose,
        "workers": workers,
    }


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Shift the datetime of photos and videos by a specified offset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run interactively (guided prompts)
  python shift_time_cli.py

  # Shift all files in a folder by +8 hours
  python shift_time_cli.py --input ./drone_photos --shift +08:00:00

  # Dry run to preview changes
  python shift_time_cli.py --input ./drone_photos --shift +08:00:00 --dry-run

  # Shift by -30 minutes with backup
  python shift_time_cli.py --input ./photos --shift -00:30:00 --backup

  # Shift by 1 day 2 hours with logging
  python shift_time_cli.py --input ./photos --shift +1:02:00:00 --log-file shift.log
        """,
    )

    parser.add_argument(
        "--input",
        required=False,
        type=Path,
        help="Folder with photos/videos to shift (interactive mode if omitted)",
    )
    parser.add_argument(
        "--shift",
        required=False,
        type=str,
        help="Time shift amount: [+|-][DD:]HH:MM:SS (e.g., +08:00:00, -00:30:00, +1:12:00:00)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without writing",
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
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel workers for processing (default: 4). Use 1 for sequential processing.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="exiftool subprocess timeout in seconds (default: 60). Increase for very large files.",
    )

    args = parser.parse_args()

    # Check if running in interactive mode (no required args provided)
    if args.input is None or args.shift is None:
        try:
            # Prompt user for configuration
            config = prompt_for_interactive_mode()
            # Convert to args-like object
            args.input = config["input"]
            args.shift = config["shift"]
            args.extensions = config["extensions"]
            args.recursive = config["recursive"]
            args.backup = config["backup"]
            args.dry_run = config["dry_run"]
            args.log_file = config["log_file"]
            args.verbose = config["verbose"]
            args.workers = config["workers"]
        except KeyboardInterrupt:
            print("\nCancelled by user")
            return 1

    # Parse shift argument if it's a string (from command line)
    if isinstance(args.shift, str):
        try:
            args.shift = parse_shift(args.shift)
        except TimeShiftError as e:
            print(f"Error parsing shift: {e}")
            return 1

    # Setup logging with unique filename if log file already exists
    if args.log_file:
        args.log_file = get_unique_log_path(args.log_file)
    setup_logging(log_file=args.log_file, verbose=args.verbose)

    try:
        # Verify exiftool
        logger.info("Checking for exiftool...")
        check_exiftool()

        # Parse extensions
        extensions = [ext.strip().lstrip(".").lower() for ext in args.extensions.split(",")]

        # Process input
        logger.info(f"Processing {args.input.name}...")
        if args.input.is_file():
            # Single file
            success = write_time_shift(
                args.input,
                args.shift,
                backup=args.backup,
                dry_run=args.dry_run,
                timeout=args.timeout,
            )
            return 0 if success else 1

        elif args.input.is_dir():
            # Directory
            shifted, skipped, failed = process_directory(
                args.input,
                shift_td=args.shift,
                dry_run=args.dry_run,
                backup=args.backup,
                recursive=args.recursive,
                extensions=extensions,
                workers=args.workers,
                timeout=args.timeout,
            )

            logger.info("=" * 60)
            if args.dry_run:
                logger.info(f"DRY RUN SUMMARY: {shifted} would be shifted, {skipped + failed} skipped/failed")
            else:
                logger.info(
                    f"SUMMARY: {shifted} shifted, {skipped} skipped, {failed} failed"
                )
            logger.info("=" * 60)

            return 0 if (failed == 0 and shifted > 0) else (1 if failed > 0 else 0)

        else:
            logger.error(f"{args.input} is neither a file nor a directory")
            return 1

    except ExifToolNotFoundError as e:
        logger.error(str(e))
        return 1
    except TimeShiftError as e:
        logger.error(f"Time shift error: {e}")
        return 1
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=args.verbose)
        return 1


if __name__ == "__main__":
    sys.exit(main())
