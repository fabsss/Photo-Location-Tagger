# Photo-Location-Tagger

A Python CLI tool to geotag photos and videos using Google Location History timeline data.

## Features

- Smart timezone handling without timezone guessing
- Multiple timeline format support (semanticSegments, legacy, timelineObjects)
- **Comprehensive format support**: JPG, PNG, TIFF, WebP, RAW files from all major camera brands, and videos
- Backup mode keeps original files
- Dry-run mode to preview changes before committing
- Interactive mode for easy configuration
- Detailed logging (INFO and DEBUG)


## Installation

### Requirements
- Python 3.10+
- exiftool (system command)

### Install exiftool
- Windows: winget install exiftool
- macOS: brew install exiftool
- Linux: sudo apt-get install libimage-exiftool-perl

### Install Python dependencies
```bash
pip install -r requirements.txt
```

## Usage

### Interactive Mode (Recommended)

Simply run the script with no arguments for guided prompts:

```bash
python tagger_cli.py
```

You'll be prompted to:
1. Select your timeline.json file (use `.` for current directory, or full path)
2. Choose photos/videos to geotag
3. Configure time margin, file extensions, and other options
4. Preview changes in dry-run mode before committing

**Tips for interactive mode paths**:
- **For photo folders**: `.` (current dir), `.\subfolder`, or `C:\Users\name\Photos`
- **For log files**: Enter a **filename**, not a directory
  - ✅ Correct: `tagger.log` or `./logs/tagger.log`
  - ❌ Wrong: `.` or `./logs` (these are directories)
- Use `.\subfolder` (Windows) or `./subfolder` (macOS/Linux) for subdirectories
- Use absolute paths like `C:\Users\name\Photos` or `/Users/name/Photos` when needed

### Command-line Mode

For scripting or automation:

```bash
# Geotag a single photo
python tagger_cli.py --timeline timeline.json --input photo.jpg

# Geotag all JPEGs in a folder with 60-minute margin
python tagger_cli.py --timeline timeline.json --input ./trip --recursive --time-margin 60

# Process with 8 parallel workers (faster on multi-core systems)
python tagger_cli.py --timeline timeline.json --input ./photos --workers 8

# Sequential processing (original behavior, use if parallel causes issues)
python tagger_cli.py --timeline timeline.json --input ./photos --workers 1

# Preview without making changes (dry-run)
python tagger_cli.py --timeline timeline.json --input ./photos --dry-run

# Save detailed log to file
python tagger_cli.py --timeline timeline.json --input ./photos --log-file tagger.log --verbose
```

#### Path Shortcuts

If the timeline and photos are in the **same directory** as the script:

**Windows:**
```powershell
# Current directory (same folder as script)
python tagger_cli.py --timeline timeline.json --input .

# Subdirectory in current location
python tagger_cli.py --timeline timeline.json --input .\subfolder

# Absolute path
python tagger_cli.py --timeline C:\Users\YourName\timeline.json --input C:\Users\YourName\Photos
```

**macOS/Linux:**
```bash
# Current directory (same folder as script)
python tagger_cli.py --timeline timeline.json --input .

# Subdirectory in current location
python tagger_cli.py --timeline timeline.json --input ./subfolder

# Absolute path
python tagger_cli.py --timeline /Users/yourname/timeline.json --input /Users/yourname/Photos
```

**Note**: Python accepts both `/` and `\` on Windows, but the native separator is `\`.

#### Paths with Spaces in Folder Names

**In command-line mode**, wrap the path in **quotes**:

**Windows:**
```powershell
# Subdirectory with space
python tagger_cli.py --timeline timeline.json --input ".\My Photos"

# Absolute path with spaces
python tagger_cli.py --timeline "C:\Users\John Doe\timeline.json" --input "C:\Users\John Doe\My Photos"
```

**macOS/Linux:**
```bash
# Subdirectory with space
python tagger_cli.py --timeline timeline.json --input "./My Photos"

# Absolute path with spaces
python tagger_cli.py --timeline "/Users/John Doe/timeline.json" --input "/Users/John Doe/My Photos"
```

**In interactive mode**, just type the path normally - spaces are no problem:
```
Enter path to timeline.json: C:\Users\John Doe\timeline.json
Enter path to photo/folder: .\My Photos
```

## Supported Formats

### Images
- **Standard**: JPG, JPEG, PNG, TIFF, TIF, WebP
- **Raw (Adobe)**: DNG
- **Raw (Sony)**: ARW, SRF, SR2
- **Raw (Canon)**: CR2, CR3, CRW
- **Raw (Nikon)**: NEF, NRW
- **Raw (Fujifilm)**: RAF
- **Raw (Panasonic/Lumix)**: RW2, RWL
- **Raw (Olympus)**: ORF
- **Raw (Pentax)**: PEF, PTX
- **Raw (Epson)**: ERF
- **Raw (Samsung)**: SRW
- **Raw (GoPro)**: GPR
- **Raw (Hasselblad)**: 3FR

### Videos
- MP4, MOV

All formats are processed by default. Use `--extensions` to customize.

## Options

- --timeline FILE: Google Timeline JSON file (optional if running interactively)
- --input PATH: File or folder to process (optional if running interactively)
- --time-margin N: Max time difference in minutes (default: 30)
- --dry-run: Show what would be tagged without writing
- --log-file FILE: Write detailed log to file
- --backup: Keep _original backup files
- --recursive: Process subfolders recursively
- --extensions EXT: Comma-separated extensions (default: all supported formats listed above)
- --workers N: Number of parallel workers for processing (default: 4). Use 1 for sequential processing (equivalent to original behavior)
- -v, --verbose: Enable DEBUG level logging

### Performance Notes

**Parallel Processing (default: 4 workers)**
- Uses a thread pool to process files in parallel after batch-reading timestamps
- Recommended for SSD drives and typical use (10x+ faster than sequential)
- Each worker runs independently without synchronization overhead

**Sequential Processing (--workers 1)**
- Processes files one at a time (original behavior)
- Useful if you encounter issues with parallel execution
- Identical output and tagging logic as default

**Batch Timestamp Reading**
- All approaches use batch exiftool reads (500 files → 3 subprocess calls instead of 500)
- Reduces CPU/I/O overhead regardless of worker count
- Per-file error isolation (one malformed file doesn't fail the batch)

### Log File Management

When using `--log-file`, the tool automatically creates unique filenames if the file already exists:

- **First run**: `tagger.log`
- **Second run**: `tagger.log.1`
- **Third run**: `tagger.log.2`
- And so on...

This ensures you never lose log history. Each run gets its own log file, making it easy to:
- Compare results across multiple runs
- Debug issues from different processing attempts
- Keep a complete audit trail without manual renaming

Example:
```bash
# First run creates tagger.log
python tagger_cli.py --timeline timeline.json --input ./photos --log-file tagger.log

# Second run creates tagger.log.1 (tagger.log is preserved)
python tagger_cli.py --timeline timeline.json --input ./photos --log-file tagger.log

# Third run creates tagger.log.2
python tagger_cli.py --timeline timeline.json --input ./photos --log-file tagger.log
```

## How It Works

Compares naive local times directly - no timezone guessing required.

The GPS point provides UTC time plus timezone offset, which we convert to local time. The image EXIF provides naive local time. These match directly without timezone conversion ambiguity.

### Timezone Handling

Google's Timeline export can be **inconsistent** with timezone data:

- **Some segments have** `startTimeTimezoneUtcOffsetMinutes` (e.g., 660 for UTC+11) ✓
- **Some segments don't**, but timestamps have embedded timezone (e.g., `+01:00` in ISO string) ❌

The tool handles this intelligently:

1. **Primary source**: Uses `startTimeTimezoneUtcOffsetMinutes` when available (most reliable)
2. **Fallback**: If missing, extracts timezone from the embedded ISO timestamp
3. **Propagation**: If a segment has no timezone offset, uses the **last known timezone** from previous segments (this handles Google's inconsistency)

**Result**: Photos get tagged with correct timezone even if your timeline.json has missing or conflicting timezone data.

### Known Limitation: Multi-timezone Travel

When traveling across multiple time zones, there is a potential edge case where photos cannot be uniquely matched to GPS points:

- **The issue**: `local_time` (the naive datetime used for matching) is not globally unique across timezone boundaries.
  - Example: a photo taken in Melbourne at 08:00 AM (UTC+11) and a photo taken in London at 08:00 AM (UTC+0) on the same day produce identical `local_time` values (2024-03-15 08:00:00).
  - The binary search algorithm cannot distinguish between these two different moments in absolute time.

- **When it matters**: If you travel across time zones and take photos in both zones on the same calendar date, some photos might be matched to GPS points from the wrong timezone leg.

- **Workaround**: Process photos from each timezone leg separately:
  1. Export one leg at a time (e.g., all Melbourne photos, then all London photos)
  2. Use separate timeline.json exports if available
  3. Or accept the small risk if the trip is short and timezone changes are minor

- **When it works fine**: Single-timezone trips, or when all photos and GPS points fall within the same timezone window.

## Testing

```bash
pytest tests/ -v
pytest tests/ --cov=tagger --cov-report=html
```

## Project Structure

```
Photo-Location-Tagger/
├── tagger/
│   ├── __init__.py
│   ├── utils.py              # Coordinate normalization, timezone utilities
│   ├── timeline_parser.py    # Parse timeline.json to list of GPSPoint
│   ├── location_finder.py    # Binary-search closest GPSPoint
│   └── exif_writer.py        # Write GPS and OffsetTimeOriginal
├── tagger_cli.py             # CLI entry point
├── tests/
│   ├── conftest.py           # Pytest fixtures
│   ├── fixtures/
│   │   └── sample_timeline.json
│   ├── test_timeline_parser.py
│   ├── test_location_finder.py
│   ├── test_exif_writer.py
│   └── test_e2e.py
├── requirements.txt
└── README.md
```

## Getting Your Google Timeline

**Note:** As of 2025, Google Location History is no longer available in Google Takeout. You must export it directly from your device.

### How to export Location History on Android/iOS:

1. Open **Google Maps** on your phone
2. Tap your **profile picture** → **Settings** → **Location Settings**
3. Tap **Timeline** (or **Your timeline**)
4. Tap the **menu icon** (⋮) → **Settings and privacy** → **Export your timeline**
5. Select the date range and format (choose **JSON**)
6. Download the exported file to your computer
7. The file will be named something like `timeline.json` or `timeline-YYYY.json`

### Using the exported file:

Place the `timeline.json` file in an accessible location and point the tool to it:
```bash
python tagger_cli.py --timeline /path/to/timeline.json --input ./photos
```

Or run interactively (no parameters needed):
```bash
python tagger_cli.py
```

## Error Handling

Gracefully handles: missing files, malformed JSON, missing timestamps, no GPS matches, exiftool errors, permission issues.

See log output with --log-file for detailed debugging.

## Troubleshooting

### "exiftool timed out writing" on large video files
**Cause**: Large 4K video files can take longer than the default timeout to process.

**Solution**: The tool now uses:
- 60-second timeout for writes (suitable for 4K video files)
- 30-second timeout for reads
- These are set automatically; no configuration needed

If you encounter timeouts on extremely large files (>5GB), the timeouts can be increased by modifying `tagger/exif_writer.py` and raising the `timeout=60` values.

### "Temporary file already exists" error
**Cause**: If exiftool is interrupted or crashes during writing, it leaves a temporary file (`<filename>_exiftool_tmp`) that blocks future writes to the same file.

**Solution**: The tool automatically cleans up stale temporary files before attempting writes. If you manually need to clean them:
```bash
# Remove all stale exiftool temp files in a directory
find . -name "*_exiftool_tmp" -delete
```

### DNG files not being geotagged
**Cause**: DNG (raw) files from some cameras show maker note parsing warnings, which exiftool previously treated as fatal errors.

**Solution**: The tool now uses the `-api ignoreMinorErrors=1` flag, which:
- Treats maker note warnings as non-fatal
- Still writes GPS coordinates and timezone data successfully
- Matches behavior of ExiftoolGUI and other professional tools

DNG files should now geotag successfully alongside JPGs.

### Video files showing "No readable timestamp found"
**Cause**: MP4/MOV video files use QuickTime tags instead of EXIF tags for metadata, which older code didn't support.

**Solution**: The tool now:
- Detects video files (.mp4, .mov, .m4v) automatically
- Reads QuickTime tags (CreateDate, MediaCreateDate) for videos
- Falls back to EXIF tags for image files
- Works seamlessly in both single-file and batch mode

Video timestamps should now be found and processed normally.

## License

MIT
