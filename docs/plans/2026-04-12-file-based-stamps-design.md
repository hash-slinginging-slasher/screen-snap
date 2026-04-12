# File-Based Stamps — Design Document

**Date:** 2026-04-12
**Status:** Approved

## Summary

Replace the programmatic `_draw_stamp()` system with file-based stamp loading from a `stamps/` folder. SVG files rendered via `cairosvg`, PNG files loaded natively with Pillow. Subfolders define categories.

## Folder Structure

```
stamps/
  status/
    check.svg
    x.svg
    warn.svg
    info.svg
    question.svg
  reaction/
    thumbs-up.png
    heart.png
```

- Folder lives next to the script (or next to the EXE when frozen)
- Each subfolder = category in the dropdown
- Filename (without extension) = display name
- Files sorted alphabetically within each category

## Loading Behavior

- Scan `stamps/` on stamp tool activation (lazy, not at startup)
- SVGs: `cairosvg.svg2png(url=path, output_width=size, output_height=size)` → `Image.open(BytesIO(...))`
- PNGs: `Image.open(path).resize((size, size), Image.LANCZOS)`
- Auto-install `cairosvg` on first SVG load (same pattern as other deps)
- Cache loaded images keyed by `(filepath, render_size)` to avoid re-reading
- If `stamps/` empty or missing → status bar message "No stamps found"

## What Changes

**Removed:**
- `STAMP_CATEGORIES` class constant
- `_draw_stamp()` static method (all 14 programmatic icons)

**Rewritten:**
- `_update_stamp_buttons()` — reads file list from current category subfolder
- `_select_stamp()` — stores file path instead of stamp name
- `_place_stamp()` — loads image file instead of calling `_draw_stamp()`, same 4x supersample + shadow pipeline

**Unchanged:**
- Stamp properties panel layout (category dropdown, stamp buttons, size spinner)
- Shadow/composite/LANCZOS downsample rendering pipeline
- Overflow menu entry and keyboard shortcut (M)

## Initial SVG Files

Extract the 5 icons from `stamps/screenshot_stamp_icons.html` into `stamps/status/`:
- `check.svg` (green circle + white checkmark)
- `x.svg` (red circle + white X)
- `warn.svg` (amber circle + white exclamation)
- `info.svg` (blue circle + white i)
- `question.svg` (purple circle + white ?)
