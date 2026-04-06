# GEMINI.md - Project Context: ScreenSnap

## Project Overview
**ScreenSnap** is a lightweight, portable screenshot and annotation utility specifically designed for **Windows 10/11**. It follows a "no-install" philosophy, allowing it to be dropped into any folder or added to the Windows PATH for immediate use.

- **Primary Language:** Python 3.10+
- **GUI Framework:** `tkinter`
- **Image Processing:** `Pillow` (PIL)
- **Clipboard Support:** `pyperclip`
- **Distribution:** Standalone Windows Executable via `PyInstaller`

## Architecture & Design Patterns
The project adheres to a strict **single-file application logic** model.
- **Main Logic:** `screensnap.py` contains all application code (~2800 lines).
- **Persistent Tk Root:** Uses a single `_app_root` (via `_get_root()`) to avoid "pyimage" errors when switching between launcher, region selector, and editor windows.
- **Auto-Dependency Management:** `ensure_dependencies()` at the top of `screensnap.py` installs required packages (`Pillow`, `pyperclip`) on the first run if they are missing.
- **DPI Awareness:** Enables per-monitor DPI awareness via `ctypes.windll.shcore.SetProcessDpiAwareness(1)` to ensure coordinate consistency across multiple monitors.

## Key Components (within `screensnap.py`)
| Component | Purpose |
|---|---|
| `SettingsManager` | Handles `settings.ini` configuration (save path, format, auto-save). |
| `LauncherWindow` | The main GUI dashboard (Full/Region capture, Settings, Library). |
| `RegionSelector` | Transparent overlay for drag-to-select screen regions. |
| `AnnotationEditor` | The core editor (rect, line, circle, crop, text tools, color palette). |
| `LibraryBrowser` | Interface for browsing and managing previously saved screenshots. |

## Building and Running

### Development (Python)
Run the tool directly using the Python interpreter or the provided batch file:
```cmd
python screensnap.py [mode] [--save PATH]
# OR
screensnap.bat [mode]
```
- **Modes:** `full` (fullscreen), `region` (region selector), or empty (launcher).

### Production (EXE)
Build a standalone executable using the build script:
```cmd
build-exe.bat
```
This script uses `pyinstaller` to create `dist/ScreenSnap.exe` with bundled dependencies and the `screensnap.ico` icon.

## Development Conventions
- **Single File:** Do not split `screensnap.py` into multiple modules unless explicitly requested.
- **Portability:** Ensure no files are created outside the application directory (except for user-defined save paths).
- **Windows Focus:** Utilize `ctypes` for Windows-specific functionality (DPI awareness, multi-monitor metrics).
- **No External Assets:** Icons and other assets should be generated programmatically (e.g., `create-icon.py`) rather than requiring external binary files during development.

## Key Files
- `screensnap.py`: Core application logic.
- `settings.ini`: Local configuration storage.
- `screensnap.bat`: Entry point for Python execution.
- `build-exe.bat`: Build pipeline for the standalone EXE.
- `README.md`: Comprehensive user documentation.
- `CLAUDE.md`: Specialized developer guidance and architectural map.
