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
1. Select your timeline.json file
2. Choose photos/videos to geotag
3. Configure time margin, file extensions, and other options
4. Preview changes in dry-run mode before committing

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
