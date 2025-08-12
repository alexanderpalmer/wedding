# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based image processing project for converting high-resolution wedding photos into web-optimized PNG files. The main script `png_web_exporter.py` handles batch resizing, format conversion, and PNG optimization.

## Key Commands

### Running the Image Converter
```bash
python png_web_exporter.py <input_directory> <output_directory> [options]
```

Common usage patterns:
```bash
# Convert all high-res images to 50% size (default)
python png_web_exporter.py . converted

# Convert with custom scale factor
python png_web_exporter.py . converted --scale 0.3

# Force conversion even if target wouldn't be smaller
python png_web_exporter.py . converted --force

# Verbose output
python png_web_exporter.py . converted -v

# Custom resolution thresholds
python png_web_exporter.py . converted --min-width 2000 --min-height 1500
```

### Dependencies
```bash
pip install pillow
```

## Architecture Notes

### Core Processing Pipeline
The script processes images through several stages:
1. **Input Discovery**: Recursively finds images with supported extensions (.jpg, .jpeg, .png, .tif, .tiff, .bmp, .webp)
2. **Resolution Filtering**: Only processes "high-resolution" images based on configurable thresholds (default: 1600px width OR 1200px height)
3. **EXIF Processing**: Automatically rotates images based on EXIF orientation data
4. **Proportional Scaling**: Uses high-quality LANCZOS filter for resizing
5. **PNG Optimization**: 
   - Opaque images: Quantized to 256 colors for smaller file sizes
   - Images with transparency: Preserved without quantization but with compression optimization

### Key Configuration Variables
- `SCALE`: Default scaling factor (0.5 = 50%)
- `MIN_WIDTH`/`MIN_HEIGHT`: Thresholds for "high-resolution" detection
- `INPUT_EXTS`: Supported input file extensions

### File Structure
- Source images can be in nested subdirectories
- Output maintains the same directory structure as input
- All output files are converted to PNG format regardless of input format

## Important Implementation Details

- The script strips metadata (EXIF data) during conversion by rebuilding images
- Uses conservative approach: skips images that wouldn't be meaningfully reduced in size unless `--force` is used
- Error handling continues processing other images if individual files fail
- Memory efficient: processes one image at a time using context managers