# ScreenSnap — Portable Screenshot & Annotation Tool

## Project Overview

ScreenSnap is a lightweight, portable screenshot and annotation utility built exclusively for **Windows 10/11**. It runs directly from Command Prompt with no installation wizard, auto-resolves its own Python dependencies on first launch, and is designed to be dropped into any project folder, added to the Windows PATH, or registered as a reusable shell skill.

**Version:** 1.2
**Status:** Active development — Print Screen integration added.

## Key Features

- **Full screen** and **region capture** via CLI or GUI launcher
- **Annotation editor** with rectangle, line, circle/ellipse, crop tools
- **Step tool** with teardrop, circle, square, and rounded rectangle shapes
- **Rotated teardrop shapes** - only the shape rotates, text stays upright
- **Color palette** (8 presets) and **stroke width control** (1–30 px)
- **Unlimited undo** (Ctrl+Z)
- **Save & Copy Path** — saves file and writes absolute Windows path to clipboard
- **Headless mode** via `--save <path>` CLI flag
- **Print Screen integration** - set as default PrtScn handler
- Fully **portable** — single folder, no registry writes, no AppData entries

## Planned Folder Structure

```
screensnap/
  screensnap.py                       # all application logic, single file
  screensnap.bat                      # Windows CMD entry point (Python)
  screensnap-exe.bat                  # Windows CMD entry point (Standalone .exe)
  ScreenSnap.exe                      # Standalone executable (~35 MB, in dist/ folder)
  screensnap-printscreen-monitor.py   # Background Print Screen key monitor
  build-exe.bat                       # Build script to create ScreenSnap.exe
  install-printscreen-monitor.bat     # Set up Print Screen interception
  stop-printscreen-monitor.bat        # Stop Print Screen monitor
  README.md
```

## CLI Interface

```
screensnap                            # opens launcher window
screensnap full                       # captures fullscreen, opens editor
screensnap region                     # opens region selector, opens editor
screensnap full --save C:\output.png  # headless fullscreen save, no GUI
```

## Keyboard Shortcuts

### Editor Shortcuts

| Key | Action |
|---|---|
| `R` | Rectangle tool |
| `L` | Line tool |
| `C` | Circle tool |
| `X` | Crop tool |
| `Ctrl+Z` | Undo |
| `Ctrl+S` | Save |
| `ESC` | Cancel region selection |

### System-Wide (via Background Monitor)

| Key | Action |
|---|---|
| `Print Screen` | Launch ScreenSnap with region capture |

## Dependencies (Auto-installed on first run)

| Package | Purpose |
|---|---|
| `Pillow` | Screen capture, image compositing, annotation rendering |
| `pyperclip` | Clipboard write for Save & Copy Path |
| `tkinter` | GUI framework — bundled with standard Python for Windows |
| `keyboard` | Global keyboard hook for Print Screen monitoring |
| `pystray` | System tray icon for Print Screen monitor |

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
- Out of scope for v1: arrow tool, text overlay, auto-save folder, multi-monitor selection

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

### Setting as Default Print Screen Handler
```cmd
# Install and start the background monitor
install-printscreen-monitor.bat

# Stop the monitor (if needed)
stop-printscreen-monitor.bat
```

For detailed setup instructions, see [`PRINTSCREEN-SETUP.md`](./PRINTSCREEN-SETUP.md)

## Source

Full PRD: [`screensnap-prd.md`](./screensnap-prd.md)
