# ScreenSnap Executable - Settings & Configuration Guide

## Issue Fixed ✅

The original `.exe` version had a bug where it couldn't find `settings.ini` because PyInstaller executables use a temporary extraction path for `__file__`. This has been **fixed** in `ScreenSnap_v2.exe`.

## How Settings Work

### Location of settings.ini

The `settings.ini` file is now correctly located in the **same directory as the executable**, regardless of whether you're running:
- The Python script (`screensnap.py`)
- The old executable (`ScreenSnap.exe`)
- The new executable (`ScreenSnap_v2.exe`)

### File Structure

```
screenshot-easy/
├── ScreenSnap_v2.exe      # New executable (fixed version)
├── settings.ini           # ← Settings file (same folder as .exe)
├── screensnap.py          # Python source
├── screensnap.bat         # Python launcher
└── screensnap-exe.bat     # Old .exe launcher
```

## How to Configure

### Method 1: Using the GUI (Recommended)

1. Run `ScreenSnap_v2.exe` or `screensnap-exe.bat`
2. Click the **⚙ Settings** button in the launcher window
3. Configure:
   - **Default save folder** - Browse or type the path
   - **Enable auto-save** - Check to auto-save screenshots
   - **Auto-copy file path** - Check to copy path to clipboard
   - **Image format** - Choose PNG, JPG, or BMP
4. Click **✓ Save**
5. Settings are saved to `settings.ini` in the same folder

### Method 2: Edit settings.ini Directly

Open `settings.ini` in any text editor:

```ini
[Settings]
default_save_path = D:\qwen\screenshot-easy\save
auto_save = true
auto_copy_path = true
image_format = png
```

**Settings explained:**
- `default_save_path` - Folder where auto-saved screenshots go
- `auto_save` - `true` or `false` - Auto-save after capture
- `auto_copy_path` - `true` or `false` - Copy file path to clipboard
- `image_format` - `png`, `jpg`, or `bmp`

## Auto-Save Behavior

When auto-save is enabled:

1. Capture a screenshot (full screen or region)
2. The annotation editor opens for editing
3. The image is **automatically saved** to your default folder with a timestamp
4. The file path is **copied to clipboard** (if enabled)
5. You can continue editing and save additional copies manually

**Filename format:** `screensnap_YYYYMMDD_HHMMSS.png`

## Troubleshooting

### Settings not persisting?

**Problem:** Settings reset every time I close the app

**Solution:** Make sure `settings.ini` is in the **same folder** as the executable. The executable looks for it in its own directory.

### Can't find auto-saved screenshots?

**Problem:** Where are my screenshots going?

**Solution:** 
1. Open `settings.ini` and check the `default_save_path` value
2. Make sure the folder exists and is writable
3. If the path is empty, set it to your preferred folder (e.g., `D:\qwen\screenshot-easy\save`)

### Settings dialog shows wrong path?

**Problem:** The settings dialog shows a temporary path

**Solution:** This was the bug in the OLD executable. Use `ScreenSnap_v2.exe` instead, which correctly resolves the settings file location.

## Migration from Old Version

If you were using the old `ScreenSnap.exe`:

1. Your settings may have been saved to a temporary location
2. Copy or recreate `settings.ini` in the same folder as the executable
3. Use the new `ScreenSnap_v2.exe` which has the fix

## Technical Details

### How the fix works

**Old code (broken for .exe):**
```python
SETTINGS_FILE = Path(__file__).parent / "settings.ini"
```

When running as a compiled executable, `__file__` points to a temporary extraction path like:
`C:\Users\jodel\AppData\Local\Temp\_MEI12345\screensnap.py`

**New code (works for both):**
```python
@staticmethod
def _get_base_dir():
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return Path(sys.executable).parent
    else:
        # Running as Python script
        return Path(__file__).parent
```

This detects if we're running as a frozen executable and uses `sys.executable` (the actual .exe path) instead of `__file__`.

## Version History

- **ScreenSnap.exe** (v1.0) - Initial build, settings bug
- **ScreenSnap_v2.exe** (v1.1) - Fixed settings.ini location ✅

## Next Steps

1. ✅ Delete the old locked `ScreenSnap.exe` when possible (reboot if needed)
2. ✅ Use `ScreenSnap_v2.exe` going forward
3. ✅ Configure settings via GUI or edit `settings.ini` directly
4. ✅ Test auto-save to verify it works correctly
