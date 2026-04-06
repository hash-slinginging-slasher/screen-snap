# Product Requirements Document
## ScreenSnap — Portable Screenshot & Annotation Tool

| Field | Detail |
|---|---|
| **Product Name** | ScreenSnap |
| **Version** | 1.1 |
| **Status** | Draft |
| **Platform** | Windows 10 / Windows 11 (64-bit) |
| **Runtime** | Python 3.10+ for Windows |
| **Author** | TBD |
| **Last Updated** | April 2026 |

---

### 1. Overview

ScreenSnap is a lightweight, portable screenshot and annotation utility built exclusively for Windows. It runs directly from Command Prompt with no installation wizard, auto-resolves its own Python dependencies on first launch, and is designed to be dropped into any project folder, added to the Windows PATH, or registered as a reusable shell skill.

---

### 2. Problem Statement

Developers and technical users on Windows frequently need to capture a screen area, annotate it quickly, and reference the saved file by its full path — for bug reports, documentation, or sharing via chat. Existing tools either require installation, lack path-copy functionality, or cannot be triggered from CMD.

---

### 3. Goals

- Run entirely from a CMD command on Windows with no prior setup
- Be fully portable — copy the folder, it works anywhere
- Support CLI arguments so it can be scripted or called as a skill
- Let users capture, annotate, and get the file path into clipboard in under 10 seconds

---

### 4. Non-Goals

- macOS or Linux support
- Cloud upload or sharing links
- Video or screen recording
- OCR or text extraction
- MSI / EXE installer packaging

---

### 5. System Requirements

| Requirement | Specification |
|---|---|
| **Operating System** | Windows 10 (version 1903+) or Windows 11 |
| **Architecture** | 64-bit |
| **Runtime** | Python 3.10 or higher for Windows (must be installed and on PATH) |
| **Display** | Single or multi-monitor; captures primary monitor |
| **Permissions** | Standard user — no admin rights required |
| **Network** | Internet required on first run only (pip dependency install) |
| **Disk** | ~50 MB including auto-installed dependencies |

---

### 6. Dependencies

Auto-installed on first run via `pip`. No manual action required from the user.

| Package | Purpose |
|---|---|
| `Pillow` | Screen capture, image compositing, annotation rendering |
| `pyperclip` | Clipboard write for Save & Copy Path |
| `tkinter` | GUI framework — bundled with standard Python for Windows |

---

### 7. CLI Interface

Entry point is `screensnap.bat`, invokable from any CMD window once the folder is on PATH.

```
screensnap                            # opens launcher window
screensnap full                       # captures fullscreen, opens editor
screensnap region                     # opens region selector, opens editor
screensnap full --save C:\output.png  # headless fullscreen save, no GUI
```

---

### 8. Functional Requirements

#### 8.1 Portability & Distribution

| ID | Requirement |
|---|---|
| PRT-01 | Tool ships as a single folder containing `screensnap.py`, `screensnap.bat`, and `README.md` |
| PRT-02 | `screensnap.bat` is the sole Windows entry point — no installer, no setup wizard |
| PRT-03 | On first run, `Pillow` and `pyperclip` are auto-installed silently via pip if not found |
| PRT-04 | The folder can be copied to any Windows machine with Python and run immediately |
| PRT-05 | The folder path can be added to the Windows PATH environment variable for global access |
| PRT-06 | No writes to the Windows registry, no files created outside the tool folder, no AppData entries |

#### 8.2 Capture

| ID | Requirement |
|---|---|
| CAP-01 | Full screen capture of the primary Windows display via launcher button or `full` CLI argument |
| CAP-02 | Region capture via a drag-select overlay on Windows desktop, or `region` CLI argument |
| CAP-03 | Region overlay darkens the entire Windows screen; shows live `W × H` pixel dimensions during drag |
| CAP-04 | ESC key cancels region selection and returns to launcher |
| CAP-05 | Launcher window hides itself before capture to avoid appearing in the screenshot |

#### 8.3 Annotation Editor

| ID | Requirement |
|---|---|
| ANN-01 | Rectangle tool — semi-transparent fill, solid outline |
| ANN-02 | Line tool — straight line between two points |
| ANN-03 | Circle / ellipse tool — semi-transparent fill, solid outline |
| ANN-04 | Crop tool — trims the canvas to the selected region |
| ANN-05 | Color palette with 8 preset colors |
| ANN-06 | Stroke width control, 1–30 px |
| ANN-07 | Live shape preview during mouse drag; committed to image on release |
| ANN-08 | Unlimited undo via Ctrl+Z |

#### 8.4 Save & Export

| ID | Requirement |
|---|---|
| SAV-01 | Save via Windows file dialog — supports PNG, JPG, BMP |
| SAV-02 | **Save & Copy Path** — saves the file and writes the absolute Windows path (e.g. `D:\project\screenshots\shot.png`) to the clipboard |
| SAV-03 | Headless mode: `--save <path>` skips the editor GUI and saves directly to the specified Windows path |
| SAV-04 | Ctrl+S triggers save from within the editor |
| SAV-05 | Status bar displays the full Windows path of the last saved file |

---

### 9. Keyboard Shortcuts

| Key | Action |
|---|---|
| `R` | Rectangle tool |
| `L` | Line tool |
| `C` | Circle tool |
| `X` | Crop tool |
| `Ctrl+Z` | Undo |
| `Ctrl+S` | Save |
| `ESC` | Cancel region selection |

---

### 10. Folder Structure

```
screensnap\
  screensnap.py       # all application logic, single file
  screensnap.bat      # Windows CMD entry point
  README.md
```

---

### 11. Out of Scope for v1

- Arrow annotation tool
- Text / label overlay
- Windows system tray with global hotkey
- Auto-save to a configurable output folder
- Copy image pixels to clipboard (not just path)
- `--copy` flag for headless clipboard copy
- Multi-monitor region selection
