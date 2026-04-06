# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

ScreenSnap is a portable Windows screenshot & annotation tool. All application logic lives in a **single file**: `screensnap.py` (~2265 lines). It uses tkinter for GUI, Pillow for image capture/rendering, and pyperclip for clipboard support.

## Commands

### Run (Python)
```cmd
screensnap.bat                          # GUI launcher
screensnap.bat full                     # Full screen capture
screensnap.bat region                   # Region capture
screensnap.bat full --save C:\out.png   # Headless save
```

### Run (Standalone EXE)
```cmd
screensnap-exe.bat                      # Uses dist/ScreenSnap.exe (or latest _vN.exe)
```

### Build EXE
```cmd
build-exe.bat
```
Uses PyInstaller to produce a single-file `.exe` in `dist/`. Requires `pip install pyinstaller`. The build script auto-creates the icon via `create-icon.py` if `screensnap.ico` is missing.

There is no test suite or linter configured.

## Architecture

### Single-file design
Everything is in `screensnap.py`. There are no modules, packages, or imports from local files.

### Key classes (in order of flow)

| Class | Lines | Purpose |
|---|---|---|
| `SettingsManager` | ~99 | Reads/writes `settings.ini` (INI format via `configparser`). Looks for the file next to the script, or next to the EXE when frozen. |
| `LibraryManager` | ~185 | Manages the screenshot library — tracks saved files in the default save folder. |
| `LauncherWindow` | ~237 | Main GUI window with Full/Region buttons, settings gear, and library browser. Uses a single persistent `tk.Tk` root (`_get_root()`) to avoid image reference bugs. |
| `SettingsDialog` | ~652 | Modal dialog for configuring save path, auto-save, auto-copy, and image format. |
| `RegionSelector` | ~810 | Fullscreen transparent overlay for drag-selecting a screen region. Shows live W×H dimensions. |
| `AnnotationEditor` | ~947 | The main editor with annotation tools (rect, line, circle, crop, text), color palette, stroke width, undo stack. Handles auto-save on open if enabled. |
| `LibraryBrowser` | ~1995 | Browse and manage previously saved screenshots. |

### Persistent Tk root pattern
A single `_app_root` is reused across launcher/editor/region-selector windows via `_get_root()` and `_clear_root()`. This prevents tkinter's "pyimageN doesn't exist" errors when cycling between windows.

### Settings
Stored in `settings.ini` (same directory as script/EXE). Keys: `default_save_path`, `auto_save`, `auto_copy_path`, `image_format`. A separate `config/settings.ini` exists in the dist folder for the EXE build.

### Entry points
- `main()` at bottom — parses args (`argparse`), routes to `headless_save()` or `LauncherWindow`
- `headless_save(mode, save_path)` — captures and saves without GUI

## Platform Notes

- Windows-only. Uses `ctypes.windll.user32` for multi-monitor metrics, `ImageGrab` for capture.
- Dependencies auto-install on first run via `ensure_dependencies()` at module level.
- When running as a frozen PyInstaller EXE, paths resolve via `sys._MEIPASS`.
