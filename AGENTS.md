# AGENTS.md

Quick reference for agents working in this repository.

## Run Commands

```cmd
screensnap.bat              # GUI launcher
screensnap.bat full        # Full screen capture → editor
screensnap.bat region      # Region select → editor
screensnap.bat full --save C:\out.png   # Headless (full only, no region)
screensnap-exe.bat         # Standalone EXE (prefers dist\ScreenSnap_v6.exe)
build-exe.bat              # Build standalone .exe
```

## Build Output Naming

`build-exe.bat` produces `dist/ScreenSnap.exe`, but `screensnap-exe.bat` expects `ScreenSnap_v6.exe`. After rebuilding:
- Rename `dist/ScreenSnap.exe` to `ScreenSnap_v6.exe` in `dist/`, OR
- Update `screensnap-exe.bat` to match

## No Test/Lint Suite

There is no test suite or linter. Changes must be validated manually.

## Single-File Architecture

ALL application logic is in `screensnap.py` (~2600 lines). No local imports or modules exist.

## Key Code Locations

| Purpose | Line |
|---------|------|
| Entry point (`main`) | ~2551 |
| Headless save | ~2529 |
| AnnotationEditor | ~1005 |
| Step tool (default) | ~1180 |
| RegionSelector | ~883 |

## Tool Quirks

- **Default tool is `step`** when editor opens (not rectangle/line)
- **Step tool is "eager rendering"** — pixels baked into image on placement. Dragging moves only canvas proxies, not actual pixels (until refresh)
- **Text tool is "deferred rendering"** — stays as canvas items, burned on save

## Windows-Only

Uses `ctypes.windll.user32`, `ImageGrab`, tkinter. Will not work on Linux/macOS.