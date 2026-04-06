# ScreenSnap — Portable Screenshot & Annotation Tool

**Version:** 1.1  
**Platform:** Windows 10/11 (64-bit)

## Overview

ScreenSnap is a lightweight, portable screenshot and annotation utility for Windows. It runs directly from Command Prompt with no installation wizard, auto-resolves its own Python dependencies on first launch, and is designed to be dropped into any project folder, added to the Windows PATH, or used as a reusable shell skill.

## Features

- **Full screen** and **region capture** via CLI or GUI launcher
- **Annotation editor** with rectangle, line, circle/ellipse, crop, and text tools
- **Text annotations** - Add text in a box or as a free-floating line
- **Color palette** (8 presets) and **stroke width control** (1–30 px)
- **Unlimited undo** (Ctrl+Z)
- **Auto-save** — automatically save screenshots to a default folder with timestamp
- **Save & Copy Path** — saves file and writes absolute Windows path to clipboard
- **Headless mode** via `--save <path>` CLI flag
- **Configurable settings** — set default save folder, image format, and auto-save behavior
- Fully **portable** — single folder, no registry writes, no AppData entries

## Quick Start

### Option 1: Using the Executable (No Python Required)
```cmd
# Navigate to the screensnap folder
cd path\to\screensnap

# Run the standalone executable
screensnap-exe.bat
```

### Option 2: Using Python (Original Method)
```cmd
# Navigate to the screensnap folder
cd path\to\screensnap

# Run the tool
screensnap.bat
```

### Option 3: Add to PATH (Recommended)
1. Open **System Properties** → **Environment Variables**
2. Edit the **Path** variable (User or System)
3. Add the full path to the `screensnap` folder
4. Open a new Command Prompt and run:
```cmd
screensnap-exe.bat        # Using the executable
# or
screensnap.bat            # Using Python
```

## Usage

### GUI Mode
```cmd
# Using the executable (recommended)
screensnap-exe.bat                  # Opens launcher window
screensnap-exe.bat full             # Captures full screen, opens editor
screensnap-exe.bat region           # Opens region selector, opens editor

# Using Python
screensnap.bat                      # Opens launcher window
screensnap.bat full                 # Captures full screen, opens editor
screensnap.bat region               # Opens region selector, opens editor
```

### Headless Mode (No GUI)
```cmd
# Using the executable
screensnap-exe.bat full --save C:\output.png   # Captures and saves without GUI

# Using Python
screensnap.bat full --save C:\output.png       # Captures and saves without GUI
```

## Keyboard Shortcuts

### Region Selection
| Key | Action |
|---|---|
| `ESC` | Cancel region selection |

### Annotation Editor
| Key | Action |
|---|---|
| `R` | Rectangle tool |
| `L` | Line tool |
| `C` | Circle tool |
| `X` | Crop tool |
| `T` | Text tool |
| `Ctrl+Z` | Undo |
| `Ctrl+S` | Save |

**Text Tool (Photoshop-style):**
- Click the **Text** button or press `T` to activate
- Text Properties panel appears with font, size, and color controls
- **Click** on canvas to add new text
- **Click** on existing text to select it (blue dashed box appears)
- **Drag** selected text to reposition it
- **Double-click** text to edit its content
- Change font family, size, or color in properties panel
- Click **Apply to Selected** to update selected text
- Press **Delete** key or click **Delete Selected** to remove text
- Text is automatically saved with the image

## CLI Reference

```
screensnap-exe.bat [mode] [--save PATH]

positional arguments:
  mode          Capture mode: full or region

optional arguments:
  --save PATH   Headless mode: save directly to path without GUI
```

### Examples

```cmd
# Open launcher window
screensnap-exe.bat

# Capture full screen and open editor
screensnap-exe.bat full

# Select a region and open editor
screensnap-exe.bat region

# Headless full screen capture and save
screensnap-exe.bat full --save D:\screenshots\capture.png

# Show help
screensnap-exe.bat --help
```

## Settings & Auto-Save

Click the **⚙ Settings** button in the launcher to configure:

- **Default save folder** — Screenshots are automatically saved to this location
- **Auto-save** — When enabled, screenshots are saved immediately upon capture
- **Auto-copy path** — When enabled, the file path is copied to clipboard automatically
- **Image format** — Choose between PNG, JPG, or BMP (default: PNG)

### Auto-Save Behavior

When auto-save is enabled:
1. Capture a screenshot (full screen or region)
2. The annotation editor opens for editing
3. The image is **automatically saved** to your default folder with a timestamp
4. The file path is **copied to clipboard** (if enabled)
5. You can continue editing and save additional copies manually

**Filename format:** `screensnap_YYYYMMDD_HHMMSS.png`

### Settings Storage

Settings are stored in **`settings.ini`** in the same folder as the application. This is a standard Windows INI file that you can edit manually if needed:

```ini
[Settings]
default_save_path = D:\Screenshots
auto_save = true
auto_copy_path = true
image_format = png
```

The file is portable and travels with the application folder.

## System Requirements

### For Executable Version
- **OS:** Windows 10 (version 1903+) or Windows 11, 64-bit
- **Runtime:** None required (all dependencies bundled)
- **Permissions:** Standard user — no admin rights required
- **Disk:** ~35 MB for the executable
- **Memory:** ~100 MB RAM recommended

### For Python Version
- **OS:** Windows 10 (version 1903+) or Windows 11, 64-bit
- **Runtime:** Python 3.10+ (must be installed and on PATH)
- **Permissions:** Standard user — no admin rights required
- **Network:** Required on first run only (pip dependency install)
- **Disk:** ~50 MB including auto-installed dependencies

## Dependencies

The following Python packages are auto-installed on first run:

| Package | Purpose |
|---|---|
| `Pillow` | Screen capture, image compositing, annotation rendering |
| `pyperclip` | Clipboard write for Save & Copy Path |
| `tkinter` | GUI framework — bundled with standard Python for Windows |

## Folder Structure

```
screensnap/
  screensnap.py       # All application logic (single file)
  screensnap.bat      # Windows CMD entry point (Python version)
  screensnap-exe.bat  # Windows CMD entry point (Standalone executable)
  ScreenSnap.exe      # Standalone executable (in dist/ folder after build)
  build-exe.bat       # Build script to create/rebuild ScreenSnap.exe
  README.md           # This file
```

## Building the Executable

To create or rebuild the standalone executable:

```cmd
build-exe.bat
```

This uses PyInstaller to bundle Python and all dependencies into a single `.exe` file in the `dist/` folder. The executable is approximately 35 MB in size.

**Requirements for building:**
- Python 3.10+ installed and on PATH
- PyInstaller (`pip install pyinstaller`)

The build script handles all dependencies automatically, including:
- Pillow (image processing)
- pyperclip (clipboard support)
- tkinter (GUI framework)

## Portability

### Using the Executable (Recommended)
- ✅ No Python installation required
- ✅ No installer or setup wizard
- ✅ No Windows registry writes
- ✅ No files created outside the tool folder
- ✅ No AppData entries
- ✅ Copy the folder to any Windows machine and it works
- ✅ ~35 MB standalone executable with all dependencies bundled

### Using Python Version
- ✅ No installer or setup wizard
- ✅ No Windows registry writes
- ✅ No files created outside the tool folder
- ✅ No AppData entries
- ✅ Copy the folder to any Windows machine with Python and it works

## Troubleshooting

### "Python is not found on your PATH"
- Install Python 3.10+ from [python.org](https://www.python.org/downloads/)
- During installation, check **"Add Python to PATH"**
- Restart your Command Prompt after installation

### Dependencies fail to install
- Ensure you have internet connection on first run
- Try running manually: `pip install Pillow pyperclip`
- Check that your Python version is 3.10 or higher: `python --version`

### Screenshot appears black or blank
- Some applications use hardware acceleration that may interfere
- Try using region capture instead of full screen
- Ensure ScreenSnap has necessary display permissions

## License

MIT License — Free for personal and commercial use.

## Author

TBD

---

**Built with ❤️ for Windows users who need fast, portable screenshot tools**
