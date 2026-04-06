# ScreenSnap v1.1 - Executable Version

## ✅ Settings Bug FIXED!

This version correctly reads and writes `settings.ini` from the application folder.

## Quick Start

1. **Run:** Double-click `screensnap-exe.bat` or `dist\ScreenSnap_v2.exe`
2. **Configure:** Click ⚙ Settings to set auto-save folder
3. **Capture:** Use Full Screen or Region Select
4. **Edit:** Add annotations, text, shapes
5. **Save:** Ctrl+S to save manually (or enable auto-save)

## Settings Configuration

The `settings.ini` file is located in the **same folder** as this README.

**To configure:**
- **GUI:** Click ⚙ Settings button in the app
- **Manual:** Edit `settings.ini` in Notepad

**Example settings.ini:**
```ini
[Settings]
default_save_path = D:\qwen\screenshot-easy\save
auto_save = true
auto_copy_path = true
image_format = png
```

## What Changed from v1?

**v1 (ScreenSnap.exe):**
- ❌ Settings saved to temp folder (deleted on close)
- ❌ Auto-save didn't work
- ❌ Settings didn't persist

**v2 (ScreenSnap_v2.exe):**
- ✅ Settings save to correct folder
- ✅ Auto-save works properly
- ✅ Settings persist between runs

## File Locations

```
screenshot-easy/
├── screensnap-exe.bat      ← Run this (recommended)
├── dist\ScreenSnap_v2.exe  ← The executable
├── settings.ini            ← Your settings
├── save\                   ← Auto-saved screenshots
└── README.md              ← Full documentation
```

## Need Help?

See **EXE-SETTINGS-GUIDE.md** for detailed troubleshooting.

---

**Built:** 2026-04-04
**PyInstaller:** 6.8.0
**Python:** 3.12.4
