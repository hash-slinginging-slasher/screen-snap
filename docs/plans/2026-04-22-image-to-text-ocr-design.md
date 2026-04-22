# Image-to-Text (OCR) — Design

**Date:** 2026-04-22
**Status:** Approved, ready for implementation plan

## Summary

Add OCR (Optical Character Recognition) to ScreenSnap so users can extract text from screenshots. Two entry points: an **OCR** button in the annotation editor, and a **Capture Text** button on the launcher that skips the editor entirely.

The extracted text is auto-copied to the clipboard and shown in a preview dialog where the user can review it, re-copy, or save it as a `.txt` file.

## Engine: Tesseract

- Uses **Tesseract** via the `pytesseract` Python wrapper.
- Tesseract itself is an external binary the user installs separately (not bundled).
- `pytesseract` is added to `ensure_dependencies()` so it auto-installs on first run, matching the existing Pillow/pyperclip pattern.
- Language: **English only** (hard-coded `-l eng`) for v1.

### Tesseract discovery — `find_tesseract()` helper

Resolution order:
1. `settings.ini` → `tesseract_path` (if set and points to a real file)
2. `C:\Program Files\Tesseract-OCR\tesseract.exe`
3. `C:\Program Files (x86)\Tesseract-OCR\tesseract.exe`
4. `shutil.which("tesseract")` (PATH fallback)
5. Not found → error dialog with install link + "Browse for tesseract.exe…" button that writes the chosen path to settings and retries.

## Entry Points

### Editor (`AnnotationEditor`)

- New toolbar button **"OCR"**, placed alongside the existing Copy Image button.
- OCR runs on a *rendered* copy of `self.image` — i.e. the same pipeline used on save, with deferred text and step annotations baked in via `render_text_to_image()`. The original `self.image` is not mutated.
- This means annotations added over the screenshot *are* included in the OCR input (consistent with what the user sees and would save).

### Launcher (`LauncherWindow`)

- New button **"Capture Text"** next to the existing Full / Region buttons.
- Flow: launcher `withdraw()` → `RegionSelector` → user drags region → PIL image captured → OCR runs → preview dialog → launcher `deiconify()`.
- Editor is skipped entirely — this is a pure "region → clipboard text" shortcut.

### Settings dialog

- New row: **"Tesseract path"** with a text entry + **Browse…** button (file dialog filtered to `tesseract.exe`).
- Blank value means "use auto-discovery".
- New key in `settings.ini`: `tesseract_path`.

## Result Dialog — `OCRResultDialog`

A new modal class themed to match existing dialogs.

- **Read-only `tk.Text`** widget showing the extracted text, scrollable, word-wrapped.
- **Status line** above the text: `Copied N characters to clipboard` (auto-copy happens before the dialog opens).
- **Buttons:**
  - **Copy** — re-copies current text to clipboard (for the case where the user's clipboard was overwritten between auto-copy and review).
  - **Save as .txt…** — file dialog, writes text to disk.
  - **Close**.
- **Empty / whitespace result:** skip the clipboard copy, show message `No text detected.` with only a Close button.
- **Tesseract runtime error:** show an error dialog with the exception message (not the result dialog).

## Data Flow

**Editor path:**
```
user clicks OCR
  → build rendered PIL image (self.image + deferred text/step overlays)
  → pytesseract.image_to_string(img, lang='eng')
  → strip whitespace
  → pyperclip.copy(text)
  → show OCRResultDialog
```

**Launcher path:**
```
user clicks Capture Text
  → launcher.withdraw()
  → RegionSelector → PIL image
  → pytesseract.image_to_string(img, lang='eng')
  → strip whitespace
  → pyperclip.copy(text)
  → show OCRResultDialog
  → launcher.deiconify()
```

## Error Handling

| Condition                               | Behavior                                                                                         |
|-----------------------------------------|--------------------------------------------------------------------------------------------------|
| `pytesseract` import fails              | Auto-install via `ensure_dependencies()`; if install still fails, show error dialog.             |
| Tesseract binary not found              | Dialog: "Tesseract is not installed." + install link + "Browse for tesseract.exe" which updates settings and retries. |
| `pytesseract.TesseractError` at runtime | Error dialog with the exception message.                                                          |
| Empty / whitespace result               | `No text detected.` dialog, no clipboard write.                                                   |

## Performance / Threading

OCR runs on the main thread with a transient `Running OCR…` status label. Typical screenshots (< 4 MP) complete in well under 1 second on Tesseract 5, so threading is intentionally out of scope. If latency becomes a problem later (e.g. full multi-monitor captures), the call can be moved to a background `threading.Thread`.

## Testing

No test suite exists in the repo. Manual test checklist:

- [ ] OCR button in editor extracts visible text; result dialog shows character count; clipboard contains text.
- [ ] OCR button with annotations (text + step) present — annotations are included in OCR output (expected behavior).
- [ ] Launcher **Capture Text** → region selector → result dialog; editor is not shown.
- [ ] Settings **Tesseract path** field + Browse button writes to `settings.ini` and is respected on next OCR call.
- [ ] Tesseract not installed → install-prompt dialog appears with working Browse fallback.
- [ ] Empty capture (blank area) → `No text detected.` dialog, clipboard unchanged.
- [ ] Save as .txt produces a readable UTF-8 file.

## Out of Scope (v1)

- Multi-language OCR (future enhancement — settings-configurable `lang` code).
- Word-level bounding boxes / per-word editing.
- Bundling Tesseract with the portable EXE.
- Background threading for OCR.
- Auto-detecting installed `tessdata` languages.
