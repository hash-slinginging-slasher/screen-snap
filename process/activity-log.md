## 2026-05-11

### Anchor teardrop tail tip at the click point (both editor and saved file)
**Files Changed:** `screensnap.py`

- Symptom: clicking with the teardrop step tool placed the marker's tile center at the click — but the tail tip is at the far right of the tile, so the visual "pointer" tip ended up tens of pixels away from the target the user clicked. Even after fixing the live preview, the *saved* file's tip still landed ~10 px above-left of the click.
- Root cause for the save discrepancy: the save renderer used `pad=26` for tile crops and rotated around the polygon's bbox center, while the live preview used `pad=10` and rotated around the layer center. Drawing the polygon at `(pad_save, pad_save)` shifted it 10 px relative to where the live preview drew it. Inconsistent rotation centers and layer dimensions also caused a larger discrepancy at non-zero rotations.
- Fix: (1) Added `_teardrop_anchor_in_tile(step_size, rotation, model_x, model_y)` that computes where any model-space point lands in the final downsampled tile, using the same rotate-with-expand math as the digit anchor. (2) `add_step_element` now places the tile for teardrops so the tail tip (model `(135, 50)`) lands at the click; other shapes still use `x - half_size`. (3) Refactored `_render_step_image` to delegate to a new `_render_step_pil` that returns a PIL Image. The save renderer reuses `_render_step_pil` for teardrops and composites at `(elem['x'], elem['y'])`, so the saved file uses the exact same pipeline (pad, rotation center, dimensions) as the live preview. Non-teardrop shapes still go through the existing save-render path (their save placement was already correct).
- Not changed: rotating or resizing an already-placed teardrop still pivots around the tile origin, so the tip moves on the canvas. Can be revisited if it becomes annoying.

**Deployment:** Not deployed

---

### Fix step tool digit appearing outside teardrop bulb
**Files Changed:** `screensnap.py`

- Symptom: at certain rotations the step number rendered outside the teardrop, near the tail tip or off the shape entirely (visible on `screensnap_20260511_101910.png`'s "Step 1").
- Root cause: `_render_step_image()` (live preview) and the save-time step renderer both drew the digit at the tile's geometric center, but the teardrop's bulb is offset from the polygon bbox center. Already wrong unrotated; rotation around the tile center swings the bulb around while the digit stayed put, so it could land outside the bulb entirely.
- Fix: for `shape == 'teardrop'`, anchor the digit at the centroid of the bulb half-disk (model `(50 − 4r/3π, 50)` ≈ `(33, 50)`) rather than the arc center / bbox center. Initially used the arc center `(50, 50)` but that lands on the bulb's diameter — the boundary with the tail — so the digit visually straddled the bulb/tail edge. The half-disk centroid is the visual middle of the round portion. The anchor is tracked through the same PIL `rotate(-rotation, expand=True)` transform (rotating the layer corners to recover the expand offset), then scaled to the final tile dimensions. Rotation forward-transform verified against PIL within ~1 px across 0°/30°/45°/90°/180°/270°/-60°. Non-teardrop shapes still anchor at tile center.

**Deployment:** Not deployed

---

## 2026-05-08

### Fix Save & Copy / Copy Image silently no-op'ing under clipboard contention
**Files Changed:** `screensnap.py`

- Symptom: pressing Save & Copy or Copy Image often left the OLD clipboard contents in place — pasting still produced previously-copied text/image even after spamming the buttons. The file did get saved to disk, but the clipboard was never updated.
- Root cause: both code paths called the Win32 clipboard API (`OpenClipboard` for Copy Image, `pyperclip.copy` for Save & Copy) without retry or return-value checking. Whenever another process briefly held the clipboard — Windows clipboard history (Win+V), browsers, password managers, OneDrive, clipboard tools — `OpenClipboard` returned 0 and the rest of the call chain became a silent no-op.
- Fix: added `_open_clipboard_with_retry()` (10× attempts, 30 ms apart) and `_set_clipboard_text()` helpers on the editor. Rewrote `copy_image_to_clipboard()` to use the retry, check `SetClipboardData`'s handle, and surface a real error dialog when the clipboard is genuinely unavailable. Replaced `pyperclip.copy()` in `save_and_copy()`, `auto_save_to_default()` (auto-copy path), `ocr_current_image()` (OCR text), and `share_to_imgbb()` (ImgBB URL) with the retry-aware helper, so all editor-side clipboard writes either succeed or report a clear "clipboard busy" status.
- Sites outside `AnnotationEditor` (`LauncherWindow.capture_text_to_clipboard`, `OCRResultDialog.copy_to_clipboard`) still use plain `pyperclip.copy` — same vulnerability exists, but those weren't reported and are in different classes that don't have access to the helper.

**Deployment:** Not deployed

---

### Fix step tool "mirror image" / ghost duplicates on save
**Files Changed:** `screensnap.py`

- Symptom: a saved screenshot showed step "1" rendered twice at slightly offset positions (looked like "11"). Triggered when any save-like action ran more than once during a session, especially after dragging a step between calls.
- Root cause: `render_annotations_to_image()` was mutating `self.image` in place (alpha-compositing every step/shape/text/bubble/stamp onto it). It is invoked from 6 entry points (auto-save, manual save, copy-to-clipboard, OCR, save-and-copy, share-to-imgbb), and never restored a clean baseline. Repeated calls re-baked elements on top of already-baked pixels — and dragged elements left ghosts at their old positions.
- Fix: refactored `render_annotations_to_image()` to operate on a local `out = self.image.copy()` and **return** the composed image instead of mutating `self.image`. `self.image` now stays pristine (only crop/blur destructively modify it), so re-rendering is idempotent. Updated all 6 callers to use the returned image, including the library-copy save path inside `save()`.

**Deployment:** Not deployed

---

## 2026-05-03

### Center editor action buttons
**Files Changed:** `screensnap.py`

- Editor toolbar's `actions_frame` (SHARE | SAVE & COPY | OCR | COPY IMAGE | REGION | LAUNCHER) was packed with `side='right'`, pinning the whole group to the right edge of the second toolbar row. Changed to `anchor='center'` so the group sits in the middle of the row.
- Inner buttons keep `side='right'` so left-to-right visual order is unchanged.
- Rebuilt `dist\ScreenSnap.exe` (20 MB) and `installer-output\ScreenSnap-Setup-1.1.0.exe` (67 MB).

**Deployment:** Built locally

---

### Fix 3 GB EXE bloat — exclude unused heavy packages
**Files Changed:** `ScreenSnap.spec`, `ScreenSnapMonitor.spec`, `build-exe.bat`

- Symptom: `dist\ScreenSnap.exe` was 3,008 MB (and the installer 3,045 MB), causing PC lag during use, slow PrtSc launches (onefile extraction took ages), and a broken installer experience.
- Root cause: `excludes=[]` was empty in both `.spec` files, and `build-exe.bat` was regenerating the spec from CLI args (which discards spec edits). PyInstaller's analysis of `screensnap.py`'s deps was transitively pulling in matplotlib, numpy, nltk, playwright, pygame, yt_dlp, torch, IPython, sqlalchemy, lxml, etc. from the user's global `site-packages` — none of which are used by ScreenSnap. Confirmed via `build/ScreenSnap/PKG-00.toc` (82,290 entries, 3 GB `ScreenSnap.pkg`).
- Added explicit `excludes=[...]` list to both `ScreenSnap.spec` and `ScreenSnapMonitor.spec` (matplotlib, numpy, scipy, pandas, nltk, lark, torch, accelerate, transformers, sklearn, playwright, selenium, pygame, yt_dlp, cv2, IPython, jupyter*, prompt_toolkit, sqlalchemy, lxml, fastapi/flask/django/etc., requests, lxml, pytest, sphinx, cython, setuptools, pip; monitor also excludes tkinter).
- Switched `build-exe.bat` to invoke `pyinstaller --clean --noconfirm ScreenSnap.spec` and the equivalent for the monitor — so future rebuilds honor the spec exclude list instead of overwriting it.
- Smoke-tested: `dist\ScreenSnap.exe --help` runs cleanly, confirming PIL/pyperclip/tkinter/pytesseract still resolve at runtime.
- Also removed stale `.printscreen-monitor.lock` (held dead PID 25604).

**Result sizes:**
- `dist\ScreenSnap.exe`: 3,008 MB → **20 MB** (~150×)
- `dist\ScreenSnapMonitor.exe`: 28 MB → **16 MB**
- `installer-output\ScreenSnap-Setup-1.1.0.exe`: 3,045 MB → **67 MB** (~45×)
- ~6 GB freed by deleting old `build/` and `dist/`

**Deployment:** Built locally; new installer at `installer-output\ScreenSnap-Setup-1.1.0.exe`

---

## 2026-05-02

### Editor toolbar: split actions onto own row
**Files Changed:** `screensnap.py`

- The editor packed Tools/History/Colors (left) and 6 action buttons including SAVE & COPY (right) all in one row inside `create_toolbar` (~line 2290). On smaller screens the left groups consumed all the width and clipped the right-side actions off the visible toolbar.
- Wrapped the toolbar in a `container` Frame and moved the actions group to a dedicated second row (`actions_bar`) packed below the main toolbar. Same right-aligned button order (SHARE | SAVE & COPY | OCR | COPY IMAGE | REGION | LAUNCHER), now always visible regardless of window width.
- Removed the now-orphaned vertical separator that previously divided colors from actions.

**Deployment:** Not deployed

---

## 2026-04-23

### Freeze screen during region selection
**Files Changed:** `screensnap.py`

- `RegionSelector` now captures a full virtual-screen snapshot (`ImageGrab.grab`) before showing the overlay, so anything moving on screen (mouse, animations, live video) stays still while the user drags a selection.
- Removed the `-alpha 0.4` window transparency that was letting the live screen bleed through; the overlay now paints a dimmed copy of the frozen snapshot as its background, and `on_drag` reveals the un-dimmed patch inside the selection rectangle for a classic "bright region, dimmed surround" look.
- `on_release` crops the result from the frozen snapshot (scaled back to its physical resolution via stored `scale_x/scale_y`) instead of re-grabbing the live screen; a live-grab fallback remains if the freeze step itself failed.

**Deployment:** Not deployed

---

## 2026-04-22

### Bundle Tesseract in portable installer
**Files Changed:** `fetch-tesseract.bat` (new), `build-exe.bat`, `build-installer.bat`, `installer.iss`, `screensnap.py`, `.gitignore`

- Added `fetch-tesseract.bat` to download Tesseract 5.5.0 from UB-Mannheim, silent-install into `build-cache/tesseract-install/`, then stage `tesseract.exe` + DLLs + `tessdata/eng.traineddata` into `tesseract/` at project root.
- `build-installer.bat` now runs `fetch-tesseract.bat` first and aborts if staging fails.
- `build-exe.bat` pip-installs `pytesseract` and passes `--hidden-import pytesseract` to PyInstaller.
- `installer.iss` ships `tesseract\*` into `{app}\tesseract\` with `recursesubdirs createallsubdirs`.
- `find_tesseract()` now checks `<app dir>/tesseract/tesseract.exe` (via new `_bundled_tesseract_path()` helper) ahead of Program Files / PATH, so the bundled binary is preferred when installed via the installer.
- `.gitignore` excludes `tesseract/` and `build-cache/`.

**Deployment:** Not deployed

---

### Image-to-Text (OCR) — Tasks 1-3 (setup)
**Files Changed:** `screensnap.py`

- Task 1: Added `pytesseract` to `ensure_dependencies()` so it auto-installs on first run.
- Task 2: Added module-level OCR helpers — `TesseractNotFoundError`, `find_tesseract(settings)` (resolves via user-configured path → common install dirs → PATH), and `run_ocr(image, settings)` (English-only `pytesseract.image_to_string`).
- Task 3: Added `tesseract_path` key to `SettingsManager.load`/`save` so the optional override persists in `config/settings.ini`.

**Deployment:** Not deployed

---

### Task 7: Add launcher Capture Text button
**Files Changed:** `screensnap.py`

- Added a `🔤  CAPTURE TEXT` `ModernButton` (variant `action`) in `LauncherWindow.__init__` directly under the REGION SELECT button (~line 788) so the new button is present on initial launcher load.
- Added a matching `🔤 Capture Text` `tk.Button` (bg `#9C27B0` purple to distinguish it from the green/blue capture siblings) in `LauncherWindow._build_launcher_ui` (~line 1049) directly under its region button. Both locations updated because `_build_launcher_ui` is invoked after every capture flow (`execute_region_capture`, `_do_open_file`, etc.) — omitting it would cause the button to vanish after the first capture.
- Added three new `LauncherWindow` methods after `execute_region_capture` (~lines 1201, 1206, 1240): `capture_text` (hides the launcher and schedules `_execute_text_capture` via `after`), `_execute_text_capture` (runs `RegionSelector`, calls module-level `run_ocr`, auto-copies extracted text via `pyperclip`, presents `OCRResultDialog`, and handles `TesseractNotFoundError` via the install prompt — always restores the launcher via `_clear_root` / `deiconify` / `_build_launcher_ui` in a `finally`), and `_prompt_install_tesseract_launcher` (yes/no messagebox → URL open or file dialog → persists `tesseract_path` to settings).
- Smoke-tested: `ast.parse` clean; module launches without crash (timed subprocess confirmed the GUI stayed up until the timeout hit).

**Deployment:** Not deployed

---

### Task 6: Add editor OCR button
**Files Changed:** `screensnap.py`

- Added `🔤 OCR` button to the `AnnotationEditor` toolbar actions_frame between COPY IMAGE and SAVE & COPY (insertion order — visual order on screen is SHARE / SAVE & COPY / OCR / COPY IMAGE / REGION / LAUNCHER because all pack `side='right'`).
- Added `AnnotationEditor.ocr_current_image` — bakes annotations via `render_annotations_to_image()`, shows a watch cursor, calls the module-level `run_ocr(self.image.copy(), self.settings)`, auto-copies extracted text to the clipboard, and presents the result in `OCRResultDialog`. Surfaces `TesseractNotFoundError` to a dedicated install prompt and any other exception as a messagebox plus status-bar error.
- Added `AnnotationEditor._prompt_install_tesseract` — yes/no messagebox pointing to the UB-Mannheim install page. "No" opens the URL via `os.startfile`; "Yes" opens a file dialog filtered for `tesseract.exe`, persists the chosen path to settings via `SettingsManager.save`, and retries the OCR call.
- Verified headlessly: `ast.parse` clean; importing the module confirms both new methods exist on `AnnotationEditor` and `run_ocr` / `TesseractNotFoundError` / `OCRResultDialog` resolve at module scope. GUI launcher launches without error (smoke-tested with a timed spawn).

**Deployment:** Not deployed

---

### Task 5: Add OCRResultDialog preview modal
**Files Changed:** `screensnap.py`

- Added top-level `OCRResultDialog` class immediately before `LibraryBrowser` — centered 600x500 modal Toplevel with a read-only Text widget and ttk scrollbar showing the extracted OCR text.
- Status line shows "No text detected.", "Copied N characters to clipboard" (SUCCESS color when `copied=True`), or "N characters" depending on state; Copy/Save-as-.txt buttons are suppressed when the text is empty, leaving only a CLOSE button.
- Smoke-tested in-process: populated and empty cases both construct, render, and close via an `after` callback; `ast.parse` clean.

**Deployment:** Not deployed

---

### Task 4: Add Tesseract path row to SettingsDialog (OCR feature)
**Files Changed:** `screensnap.py`

- Added "OCR (Image-to-Text)" section (numbered section 6) to `SettingsDialog` between the Print Screen Integration section and the Bottom Buttons block — includes a path entry bound to `self.tesseract_path_var`, a BROWSE tesseract.exe button, and an install hint label pointing to the UB-Mannheim Tesseract build wiki.
- Added `browse_tesseract` method on `SettingsDialog` adjacent to `browse_path`; opens a file dialog filtered for `tesseract.exe` and writes the chosen path back into the StringVar.
- Persisted `tesseract_path` in `SettingsDialog.save_settings` alongside the other setting writes so the value round-trips through `config/settings.ini`.
- Verified headlessly: AST parses; `SettingsDialog` constructs with `tesseract_path_var` wired; `SettingsManager` round-trips `tesseract_path` through the INI file.

**Deployment:** Not deployed

---

## 2026-04-12

### Speech Bubble Improvements
**Files Changed:** `screensnap.py`

- Replaced plain connector line+dot with proper speech bubble shape: rounded rectangle body + triangular tail
- Bubble rendered as single PIL RGBA image (no seam between tail and body)
- Tail direction adapts automatically based on anchor position relative to body
- Added bubble resize: drag bottom-right handle to change width/height
- Added anchor repositioning: drag tail tip handle to repoint the arrow
- Added explicit width/height fields to bubble elements (0 = auto-size from text)
- Three drag modes: body (move), anchor (repoint), resize (corner handle)

**Deployment:** Not deployed

---

### SVG Renderer Fix + Question Mark Centering
**Files Changed:** `screensnap.py`

- Replaced cairosvg dependency with built-in `_render_svg()` using xml.etree + ImageDraw (zero external deps)
- Handles circle, ellipse, rect, line, polyline, polygon, text with viewBox scaling
- Fixed SVG text positioning: use Pillow anchor parameter ("ms"/"rs"/"ls") for correct baseline handling
- All 5 stamp SVGs (check, x, warn, info, question) render correctly

**Deployment:** Not deployed

---

### Make Stamps and Shapes Draggable (Deferred Rendering)
**Files Changed:** `screensnap.py`

- Converted stamp tool from eager rendering (baked into image on place) to deferred rendering with `stamp_elements` list and canvas overlays
- Converted shape tools (rectangle, circle, line, arrow, highlight) from eager rendering to deferred rendering with `shape_elements` list
- All deferred elements are now draggable: click existing element to drag, click empty space to create new
- Added `_render_stamp_canvas()`, `_render_shape_canvas()`, `_find_stamp_at()`, `_find_shape_at()` methods
- Elements rendered to image on save via `render_annotations_to_image()` in correct z-order: shapes, stamps, text, bubbles, steps
- Full undo/redo support: stamp and shape elements included in `_snapshot_state()`/`_apply_state()`
- Zoom-aware: canvas overlays rebuild correctly via `_sync_overlays_to_zoom()`
- Hover cursor shows hand2 when over draggable stamps or shapes
- Blur tool remains eager-rendered (not draggable) since it transforms underlying pixels

**Deployment:** Not deployed

---

### Phase 2: Smart Move Tool
**Files Changed:** `screensnap.py`

- Added Smart Move annotation tool (shortcut V) with two-phase interaction: select a rectangular region, then drag to reposition
- Selection phase uses normal drawing behavior with green dashed rectangle preview
- Move phase shows draggable green dashed preview; on release, fills vacated area with clone-stamp border sampling and pastes region at new position
- Clone-stamp fill samples up to 16px border pixels from all four edges, blending inward with distance-weighted interpolation
- Immediate rendering: modifies self.image directly with full undo support via save_state()
- Resets smart_move state when switching tools; enabled 'smart_move' in overflow menu's _implemented_overflow set

**Deployment:** Not deployed

---

### Phase 2: Speech Bubble Annotation Tool
**Files Changed:** `screensnap.py`

- Added Speech Bubble annotation tool (shortcut B) with deferred rendering pattern (same as text tool)
- Bubbles consist of an anchor dot, connector line, semi-transparent colored rectangle, and white text
- Click to place anchor point; bubble body appears offset with editable text via prompt dialog
- Supports dragging to reposition, double-click to re-edit text, and DELETE button in properties panel
- Font size configurable via spinbox (8-48px) in bubble properties panel
- Full undo/redo support via _snapshot_state/_apply_state with bubble_elements and bubble_counter
- Bubbles rendered to image on save with RGBA alpha compositing for semi-transparent backgrounds
- Zoom-aware: canvas items re-render correctly at all zoom levels via _sync_overlays_to_zoom
- Enabled 'bubble' in overflow menu's _implemented_overflow set

**Deployment:** Not deployed

---

### Phase 2: Stamp Library Tool
**Files Changed:** `screensnap.py`

- Added Stamp Library annotation tool (shortcut M) with 14 vector icons across 4 categories (status, reaction, technical, emoji)
- Stamps rendered using 4x supersampled tiles with drop shadow, same technique as existing step tool
- Properties panel with category combobox, stamp selection buttons, and size spinbox (20-120px)
- Stamp icons: checkmark, cross, warning, info, question, thumbs_up, heart, star, bug, lock, lightbulb, gear, happy, sad, neutral
- Added STAMP_CATEGORIES class constant and _draw_stamp static method for vector icon rendering
- Enabled 'stamp' in overflow menu

**Deployment:** Not deployed

---

### Phase 2: Highlight and Blur/Pixelate Tools
**Files Changed:** `screensnap.py`

- Added Highlight tool (shortcut H): semi-transparent color overlay on rectangular region using eager rendering with RGBA alpha compositing (alpha=89)
- Added Blur/Pixelate tool (shortcut U): rectangular selection that applies pixelation or Gaussian blur to selected region
- Blur tool has properties panel with mode toggle (Pixelate/Gaussian) and intensity slider (5-30)
- Both tools enabled in overflow menu alongside Arrow
- Canvas previews: highlight uses stippled fill rectangle, blur uses dashed orange outline
- Undo/redo works via existing save_state() pattern

**Deployment:** Not deployed

---

### Phase 1: Overflow Menu + Arrow Tool
**Files Changed:** `screensnap.py`, `docs/plans/2026-04-12-annotation-tools-design.md`, `docs/plans/2026-04-12-phase1-overflow-arrow.md`

- Added "More ▾" overflow dropdown after primary tools in toolbar with 6 future tools (Arrow enabled, 5 disabled with "Coming soon")
- Keyboard shortcuts for all overflow tools: A (Arrow), M (Stamp), B (Bubble), V (Smart Move), U (Blur), H (Highlight)
- Overflow button label updates to active tool name when an overflow tool is selected
- Arrow properties panel with Style (Filled/Open) and Heads (Single/Double) toggles
- Arrow canvas preview during drag using `create_line()` with arrowheads scaling to stroke width
- Arrow rendering on release via `_draw_arrow_on_image()` with trigonometric arrowhead geometry
- Supports filled triangle and open triangle arrowhead styles, single and double-headed
- Arrow uses directional start→end coords (not bounding box) with min-length check
- Undo/redo works via existing `save_state()` pattern

**Deployment:** Not deployed

---

### Add Annotation Tools Expansion Design Doc
**Files Changed:** `docs/plans/2026-04-12-annotation-tools-design.md`

- Brainstormed and designed 6 new annotation tools: Arrow, Stamp Library, Speech Bubbles, Smart Move, Blur/Pixelate, Highlight
- Chose phased approach: Phase 1 (overflow menu + Arrow), Phase 2 (remaining tools in priority order)
- Toolbar uses overflow dropdown to avoid clutter
- All tools stay in single-file architecture

**Deployment:** Not deployed
