# ScreenSnap — Portable Screenshot & Annotation Tool

## Project Overview

ScreenSnap is a lightweight, portable screenshot and annotation utility built exclusively for **Windows 10/11**. It runs directly from Command Prompt with no installation wizard, auto-resolves its own Python dependencies on first launch, and is designed to be dropped into any project folder, added to the Windows PATH, or registered as a reusable shell skill.

**Version:** 1.1 (Draft)
**Status:** Not yet implemented — PRD only.

## Key Features

- **Full screen** and **region capture** via CLI or GUI launcher
- **Annotation editor** with rectangle, line, circle/ellipse, crop tools
- **Color palette** (8 presets) and **stroke width control** (1–30 px)
- **Unlimited undo** (Ctrl+Z)
- **Save & Copy Path** — saves file and writes absolute Windows path to clipboard
- **Headless mode** via `--save <path>` CLI flag
- Fully **portable** — single folder, no registry writes, no AppData entries

## Planned Folder Structure

```
screensnap/
  screensnap.py       # all application logic, single file
  screensnap.bat      # Windows CMD entry point (Python)
  screensnap-exe.bat  # Windows CMD entry point (Standalone .exe)
  ScreenSnap.exe      # Standalone executable (~35 MB, in dist/ folder)
  build-exe.bat       # Build script to create ScreenSnap.exe
  README.md
```

## CLI Interface (Planned)

```
screensnap                            # opens launcher window
screensnap full                       # captures fullscreen, opens editor
screensnap region                     # opens region selector, opens editor
screensnap full --save C:\output.png  # headless fullscreen save, no GUI
```

## Keyboard Shortcuts (Planned)

| Key | Action |
|---|---|
| `R` | Rectangle tool |
| `L` | Line tool |
| `C` | Circle tool |
| `X` | Crop tool |
| `Ctrl+Z` | Undo |
| `Ctrl+S` | Save |
| `ESC` | Cancel region selection |

## Dependencies (Auto-installed on first run)

| Package | Purpose |
|---|---|
| `Pillow` | Screen capture, image compositing, annotation rendering |
| `pyperclip` | Clipboard write for Save & Copy Path |
| `tkinter` | GUI framework — bundled with standard Python for Windows |

## System Requirements

- **OS:** Windows 10 (1903+) or Windows 11, 64-bit
- **Runtime:** Python 3.10+ (must be installed and on PATH)
- **Permissions:** Standard user — no admin rights required
- **Network:** Required on first run only (pip dependency install)
- **Disk:** ~50 MB including auto-installed dependencies

## Development Notes

- The entire application logic lives in a **single Python file** (`screensnap.py`)
- The `.bat` file is the sole Windows entry point
- No installer, no registry writes, no files outside the tool folder
- Out of scope for v1: arrow tool, text overlay, system tray hotkey, auto-save folder, multi-monitor selection

## Building and Running

### Using the Executable (No Python Required)
```cmd
# From the screensnap folder
screensnap-exe.bat              # or add folder to PATH and run from anywhere
screensnap-exe.bat full         # fullscreen capture
screensnap-exe.bat region       # region select
screensnap-exe.bat full --save C:\output.png  # headless save
```

### Using Python (Original Method)
```cmd
# From the screensnap folder
screensnap.bat              # or add folder to PATH and run from anywhere
screensnap.bat full         # fullscreen capture
screensnap.bat region       # region select
screensnap.bat full --save C:\output.png  # headless save
```

### Rebuilding the Executable
```cmd
build-exe.bat               # Rebuild ScreenSnap.exe using PyInstaller
```

## Source

Full PRD: [`screensnap-prd.md`](./screensnap-prd.md)
