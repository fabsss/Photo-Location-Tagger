# Photo-Location-Tagger

A Python CLI tool to geotag photos and videos using Google Location History timeline data.

## Features

- Smart timezone handling without timezone guessing
- Multiple timeline format support (semanticSegments, legacy, timelineObjects)
- **Comprehensive format support**: JPG, PNG, TIFF, WebP, RAW files from all major camera brands, and videos
- O(log n) binary search matching for fast processing
- Dry-run mode to preview changes before committing
- Detailed logging (INFO and DEBUG)
- Interactive mode for easy configuration

## Installation

### Requirements
- Python 3.10+
- exiftool (system command)

### Install exiftool
- Windows: choco install exiftool
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
- -v, --verbose: Enable DEBUG level logging

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

## License

MIT
