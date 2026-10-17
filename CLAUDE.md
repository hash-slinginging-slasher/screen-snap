# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

ScreenSnap is a portable Windows screenshot & annotation tool. All application logic lives in a **single file**: `screensnap.py` (~2593 lines). It uses tkinter for GUI, Pillow for image capture/rendering, and pyperclip for clipboard support.

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
screensnap-exe.bat                      # Prefers dist\ScreenSnap_v6.exe, then ScreenSnap_v6.exe, falls back to dist\ScreenSnap.exe
```
Note: `screensnap-exe.bat` hard-codes the `_v6` filename. After rebuilding, the new exe must be named `ScreenSnap_v6.exe` (or the batch file updated) — `build-exe.bat` produces `dist\ScreenSnap.exe`, which is only used as a last-resort fallback.

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

| Class | Starts at line | Purpose |
|---|---|---|
| `Theme` | 62 | Color/typography tokens for the "Midnight Architect" design system + global ttk style setup. |
| `ModernButton` | 166 | Pill-shaped tk.Button subclass used throughout the UI. |
| `SettingsManager` | 236 | Reads/writes `settings.ini` (INI format via `configparser`). Looks for the file next to the script, or next to the EXE when frozen. |
| `LibraryManager` | 322 | Manages the screenshot library — tracks saved files in the default save folder. |
| `LauncherWindow` | 374 | Main GUI window with Full/Region buttons, settings gear, and library browser. Uses a single persistent `tk.Tk` root (`_get_root()`) to avoid image reference bugs. |
| `SettingsDialog` | 771 | Modal dialog for configuring save path, auto-save, auto-copy, and image format. |
| `RegionSelector` | 883 | Fullscreen overlay over a frozen snapshot. Drag selects a free region (live W×H); hovering highlights the display/window/UI element under the cursor and a click captures it (see "Smart capture" below). `mode='display'` offers whole monitors only. |
| `AnnotationEditor` | 1005 | The main editor with annotation tools (rectangle, line, circle, crop, text, **step**), color palette, stroke width, undo stack. Handles auto-save on open if enabled. Default tool on open is **step** (`set_tool('step')` at line ~1180). Tool shortcuts: R/L/C/X/T/P. |
| `LibraryBrowser` | 2382 | Browse and manage previously saved screenshots as a thumbnail grid (default) or grouped list; the choice is stored as `library_view` in settings. Thumbnails are built on a worker thread and cached on disk by `ThumbnailCache` (`%LOCALAPPDATA%\ScreenSnap\thumbs`, keyed by path+mtime+size). `pick_only=True` makes it return `selected_path` instead of opening an editor — that is how the editor's 📚 LIBRARY button / Ctrl+L uses it (it prompts before discarding annotations, since the editor has no unsaved-changes tracking). |

### Smart capture (hover-to-capture in `RegionSelector`)
- Works in **physical pixels**. `capture_virtual_screen()` returns the uncropped BitBlt grab plus its origin; `capture_all_screens()` is that plus `_autocrop_black()`. Use the uncropped one whenever coordinates matter, because cropping shifts the origin.
- `ScreenMap` converts overlay (logical, system-DPI) ↔ physical coordinates **per monitor**, so mixed-DPI setups don't need a single global scale factor. The dimmed overlay image is also composed per monitor.
- Targets under the cursor, smallest first: UI elements → window → display. Scroll wheel steps through them; click captures; a drag (>4px) falls back to free-form selection.
- Windows come from `list_windows()` (EnumWindows + DWM frame bounds, snapshotted *before* the overlay exists). UI elements come from `_UIAutomation`, a dependency-free ctypes client for Windows UI Automation that runs on `_UIAWorker` (own thread, debounced, latest request wins). If UIA is unavailable the selector silently degrades to window/display targets.
- **Do not query UIA with `ElementFromPoint` through the overlay.** The overlay is topmost so it would win the hit-test, and flipping `WS_EX_TRANSPARENT` to see through it lets a click land on the app underneath. Instead walk the tree down from the window found by `list_windows()`; `_deepest()` explores *every* sibling containing the point because Chromium adds empty full-window panes next to the real UI.
- COM vtable slots used (`_com_call`): IUIAutomation 6 ElementFromHandle / 14 get_ControlViewWalker; walker 5 GetLastChildElement / 7 GetPreviousSiblingElement; element 21 ControlType / 23 Name / 43 BoundingRectangle.
- Hover code is wrapped in try/except on purpose: a hover bug must never leave the fullscreen overlay stuck.

### Persistent Tk root pattern
A single `_app_root` is reused across launcher/editor/region-selector windows via `_get_root()` and `_clear_root()`. This prevents tkinter's "pyimageN doesn't exist" errors when cycling between windows.

### Annotation rendering strategies (important — text and step tools differ)
The editor has **two different strategies** for in-progress annotations, and you must know which you are working with:

- **Shape tools** (`rectangle`, `line`, `circle`, `crop`): drawn directly into `self.image` via `ImageDraw` on mouse release (`on_canvas_release` ~line 2102). Each commit pushes `self.image.copy()` onto `self.history` for undo first.
- **Text tool** (`text_elements`, ~line 1030): **deferred rendering**. Text stays as canvas items while you edit, and is only burned into `self.image` right before save via `render_text_to_image()` (~line 2226). This lets text remain editable, movable, and re-stylable.
- **Step tool** (`step_elements`, ~line 1046): **eager rendering**. Each new step is immediately composited into `self.image` in `add_step_element()` (~line 1592) using a 4× supersampled tile (`SS = 4`) with shadow/shape layers and LANCZOS downsample — this is what gives the Snagit-like smooth edges and soft drop shadow. Canvas items (`shadow_id`, `bg_id`, `text_id`) are also created as lightweight mirrors for hit-testing and dragging.
  - **Known quirk:** because the step is already baked into `self.image`, dragging an existing step only moves the canvas proxies (`on_canvas_drag` ~line 2001); the baked pixels stay at the original position. The drag is purely visual until the next `refresh_display()` call wipes it. If you extend step editing (move/resize/recolor after placement), you will need to refactor this (e.g. store a pre-composite backup per step, or switch to deferred rendering like `text_elements`).
  - Step shapes supported: `circle`, `square`, `rounded_rect`, `teardrop` (default). The teardrop is a hand-authored Bézier polygon (`get_poly_pts` inside `add_step_element`).
  - Font size auto-scales with step size using the ratio `step_font_size = max(8, round(step_size * 0.47))` (`update_step_size` ~line 1863).

### Settings
Stored in `settings.ini` (same directory as script/EXE). Keys: `default_save_path`, `auto_save`, `auto_copy_path`, `image_format`. A separate `config/settings.ini` is expected next to the EXE in the dist folder for the EXE build (the source-tree `config/` folder is empty by design).

### Entry points
- `main()` at line 2551 — parses args (`argparse`), routes to `headless_save()` or `LauncherWindow`.
- `headless_save(mode, save_path)` at line 2529 — captures and saves without GUI. **Only `mode='full'` is supported in headless mode**; passing `region --save` will exit with an error.
- Multi-monitor capture helpers `get_all_screens_bbox()` / `capture_all_screens()` at lines 125/141 use `ctypes.windll.user32.GetSystemMetrics(76..79)` for the virtual screen rect.

## Platform Notes

- Windows-only. Uses `ctypes.windll.user32` for multi-monitor metrics, `ImageGrab.grab(bbox=..., all_screens=True)` for capture.
- **DPI awareness is set at import time** via `ctypes.windll.shcore.SetProcessDpiAwareness(1)` (with a `user32.SetProcessDPIAware()` fallback). This is required so tkinter coordinates and `ImageGrab` agree on multi-monitor setups — do not remove it.
- Dependencies auto-install on first run via `ensure_dependencies()` at module level (Pillow, pyperclip).
- When running as a frozen PyInstaller EXE, paths resolve via `sys._MEIPASS` and `SettingsManager` locates `settings.ini` next to the EXE rather than next to the script.
