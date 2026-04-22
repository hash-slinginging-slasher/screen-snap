# Image-to-Text (OCR) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Tesseract-based OCR to ScreenSnap with two entry points — an **OCR** button in the annotation editor, and a **Capture Text** button on the launcher — that auto-copy extracted text to the clipboard and show a preview dialog.

**Architecture:** Single-file additions to `screensnap.py`. Two new helpers (`find_tesseract`, `run_ocr`), one new dialog class (`OCRResultDialog`), two new methods (`AnnotationEditor.ocr_current_image`, `LauncherWindow.capture_text`), plus extensions to `SettingsManager` and `SettingsDialog` for the optional Tesseract path. `pytesseract` is added to `ensure_dependencies()`.

**Tech Stack:** Python 3, tkinter, Pillow, pyperclip, **pytesseract** (new), external **Tesseract** binary (user-installed).

**Design Doc:** `docs/plans/2026-04-22-image-to-text-ocr-design.md`

**Note on testing:** This repo has no test suite — every task uses manual smoke tests via `screensnap.bat` as verification. Keep commits small; each task ends with a commit.

---

## Task 1: Add `pytesseract` to auto-install list

**Files:**
- Modify: `screensnap.py:15-35` (the `ensure_dependencies` function)

**Step 1: Edit `ensure_dependencies`**

In the `missing` block alongside Pillow and pyperclip, add a `pytesseract` check:

```python
    try:
        import pytesseract
    except ImportError:
        missing.append('pytesseract')
```

Place it after the existing `pyperclip` try/except block (around line 27).

**Step 2: Verify install path**

Run: `screensnap.bat`
Expected: Launcher opens. If `pytesseract` was missing, console prints `Installing dependencies: pytesseract...` then continues.

Confirm in a fresh Python session:
Run: `python -c "import pytesseract; print(pytesseract.__version__)"`
Expected: Version string (e.g. `0.3.10`), no ImportError.

**Step 3: Commit**

```bash
git add screensnap.py
git commit -m "feat(ocr): auto-install pytesseract dependency"
```

---

## Task 2: Add `find_tesseract()` and `run_ocr()` module-level helpers

**Files:**
- Modify: `screensnap.py` — insert new helpers just **before** `class LauncherWindow:` (around line 661)

**Step 1: Add the helpers**

Insert this block immediately before `class LauncherWindow:`:

```python
# ── OCR helpers ────────────────────────────────────────────────────
# Tesseract is an external binary the user installs separately. We try a
# user-configured path first, then well-known install locations, then PATH.
import shutil


class TesseractNotFoundError(RuntimeError):
    """Raised when the Tesseract binary cannot be located."""


def find_tesseract(settings=None):
    """Return the absolute path to tesseract.exe, or None if not found.

    Resolution order:
      1. settings['tesseract_path'] if set and pointing to an existing file
      2. C:\\Program Files\\Tesseract-OCR\\tesseract.exe
      3. C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe
      4. shutil.which('tesseract') (PATH)
    """
    if settings:
        configured = (settings.get('tesseract_path') or '').strip()
        if configured and os.path.isfile(configured):
            return configured

    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    on_path = shutil.which('tesseract')
    if on_path:
        return on_path

    return None


def run_ocr(image: Image.Image, settings=None) -> str:
    """Run Tesseract OCR on a PIL image. Returns stripped text.

    Raises TesseractNotFoundError if the binary cannot be located.
    Raises pytesseract.TesseractError on runtime failure.
    """
    import pytesseract

    binary = find_tesseract(settings)
    if not binary:
        raise TesseractNotFoundError(
            "Tesseract is not installed or could not be located."
        )
    pytesseract.pytesseract.tesseract_cmd = binary
    text = pytesseract.image_to_string(image, lang='eng')
    return text.strip()
```

**Step 2: Smoke-test via REPL**

Run:
```
python -c "from PIL import Image, ImageDraw; from screensnap import run_ocr; img = Image.new('RGB', (400, 100), 'white'); d = ImageDraw.Draw(img); d.text((20, 30), 'Hello OCR', fill='black'); print(repr(run_ocr(img)))"
```
Expected: Prints something close to `'Hello OCR'` (Tesseract may render it with minor variance). If Tesseract is not installed, expect `TesseractNotFoundError` with the documented message.

If the user doesn't have Tesseract installed, substitute with:
```
python -c "from screensnap import find_tesseract; print(find_tesseract())"
```
Expected: `None` (and no crash).

**Step 3: Commit**

```bash
git add screensnap.py
git commit -m "feat(ocr): add find_tesseract and run_ocr helpers"
```

---

## Task 3: Extend `SettingsManager` to persist `tesseract_path`

**Files:**
- Modify: `screensnap.py:494-533` (`SettingsManager.load`)
- Modify: `screensnap.py:535-558` (`SettingsManager.save`)

**Step 1: Add the key to `load`'s `defaults` dict**

In `SettingsManager.load` (around line 499), add `'tesseract_path': ''` to the `defaults` dict. Order doesn't matter, but keep it readable — put it after `printscreen_monitor`.

**Step 2: Add the key to `save`'s `config['Settings']` dict**

In `SettingsManager.save` (around line 543), add:
```python
'tesseract_path': settings.get('tesseract_path', ''),
```
to the dict.

**Step 3: Smoke-test**

Run: `screensnap.bat`
Open Settings → Save Changes → Close.
Open `config/settings.ini` (or `%APPDATA%\ScreenSnap\config\settings.ini` for frozen builds) and confirm a `tesseract_path =` line exists (value can be blank).

**Step 4: Commit**

```bash
git add screensnap.py
git commit -m "feat(ocr): persist tesseract_path in settings"
```

---

## Task 4: Add Tesseract path row to `SettingsDialog`

**Files:**
- Modify: `screensnap.py:1164-1466` (`SettingsDialog`)

**Step 1: Add new section in `__init__`**

Locate the "Print Screen Integration" section (lines ~1282-1305). Immediately **after** it and **before** the "Bottom Buttons" block (line ~1307), insert:

```python
        # 6. OCR Section
        ocr_f = create_section(scrollable_frame, "OCR (Image-to-Text)")
        tk.Label(ocr_f,
                 text="Tesseract path (leave blank to auto-detect)",
                 font=Theme.FONT_LABEL, fg=Theme.ON_SURFACE_VARIANT,
                 bg=Theme.SURFACE).pack(anchor='w', pady=(0, 5))

        self.tesseract_path_var = tk.StringVar(
            value=settings.get('tesseract_path', '')
        )
        tess_entry_f = tk.Frame(ocr_f, bg=Theme.SURFACE_LOW, padx=2, pady=2)
        tess_entry_f.pack(fill='x', pady=(0, 10))
        tk.Entry(tess_entry_f, textvariable=self.tesseract_path_var,
                 font=("Consolas", 9),
                 bg=Theme.SURFACE_LOW, fg=Theme.ON_SURFACE,
                 insertbackground=Theme.PRIMARY,
                 relief='flat', borderwidth=8).pack(side='left', fill='x', expand=True)

        ModernButton(ocr_f, text="BROWSE tesseract.exe", variant="secondary",
                     command=self.browse_tesseract,
                     font=("Segoe UI Bold", 8)).pack(anchor='e')

        tk.Label(ocr_f,
                 text="Install Tesseract from github.com/UB-Mannheim/tesseract/wiki",
                 font=("Segoe UI", 7), fg=Theme.ON_SURFACE_VARIANT,
                 bg=Theme.SURFACE).pack(anchor='w', pady=(10, 0))
```

**Step 2: Add `browse_tesseract` method**

Immediately after `browse_path` (around line 1318), add:

```python
    def browse_tesseract(self):
        """Browse for the tesseract.exe binary."""
        file = filedialog.askopenfilename(
            title="Select tesseract.exe",
            filetypes=[("tesseract.exe", "tesseract.exe"), ("All files", "*.*")],
        )
        if file:
            self.tesseract_path_var.set(file)
```

**Step 3: Persist the value in `save_settings`**

In `save_settings` (around line 1435), add alongside the other `self.settings[...]` assignments:

```python
        self.settings['tesseract_path'] = self.tesseract_path_var.get()
```

Place it next to `self.settings['imbb_api_key']` (line 1441).

**Step 4: Smoke-test**

Run: `screensnap.bat`
Open Settings. Scroll to the new "OCR (Image-to-Text)" section. Click BROWSE and pick any file (or type a path manually). Save. Reopen Settings — the path should be persisted.

**Step 5: Commit**

```bash
git add screensnap.py
git commit -m "feat(ocr): add Tesseract path field to Settings dialog"
```

---

## Task 5: Build `OCRResultDialog` modal

**Files:**
- Modify: `screensnap.py` — insert new class just **before** `class LibraryBrowser:` (around line 5137)

**Step 1: Add the class**

```python
class OCRResultDialog:
    """Modal dialog showing OCR extracted text with Copy / Save / Close."""

    def __init__(self, parent, text, copied=False):
        self.parent = parent
        self.text = text or ""

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Extracted Text")
        self.dialog.geometry("600x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.config(bg=Theme.BACKGROUND)

        # Center
        self.dialog.update_idletasks()
        w, h = 600, 500
        x = (self.dialog.winfo_screenwidth() // 2) - (w // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (h // 2)
        self.dialog.geometry(f"{w}x{h}+{x}+{y}")

        main = tk.Frame(self.dialog, bg=Theme.BACKGROUND, padx=20, pady=20)
        main.pack(fill='both', expand=True)

        # Status line
        if not self.text:
            status_text = "No text detected."
            status_color = Theme.ON_SURFACE_VARIANT
        elif copied:
            status_text = f"Copied {len(self.text)} characters to clipboard"
            status_color = Theme.SUCCESS
        else:
            status_text = f"{len(self.text)} characters"
            status_color = Theme.ON_SURFACE_VARIANT
        tk.Label(main, text=status_text, font=("Segoe UI Bold", 10),
                 fg=status_color, bg=Theme.BACKGROUND).pack(anchor='w', pady=(0, 10))

        # Text area (read-only)
        text_frame = tk.Frame(main, bg=Theme.SURFACE_LOW, padx=2, pady=2)
        text_frame.pack(fill='both', expand=True)

        self.text_widget = tk.Text(
            text_frame, wrap='word', font=("Consolas", 10),
            bg=Theme.SURFACE_LOW, fg=Theme.ON_SURFACE,
            insertbackground=Theme.PRIMARY, relief='flat', borderwidth=8,
        )
        self.text_widget.insert('1.0', self.text)
        self.text_widget.config(state='disabled')
        scrollbar = ttk.Scrollbar(text_frame, orient='vertical',
                                  command=self.text_widget.yview)
        self.text_widget.config(yscrollcommand=scrollbar.set)
        self.text_widget.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Buttons
        btn_f = tk.Frame(main, bg=Theme.BACKGROUND)
        btn_f.pack(fill='x', pady=(15, 0))

        ModernButton(btn_f, text="CLOSE", variant="secondary",
                     command=self.dialog.destroy, width=10).pack(side='right', padx=5)

        if self.text:
            ModernButton(btn_f, text="💾 SAVE AS .TXT", variant="secondary",
                         command=self.save_to_file, width=16).pack(side='right', padx=5)
            ModernButton(btn_f, text="📋 COPY", variant="primary",
                         command=self.copy_to_clipboard, width=10).pack(side='right', padx=5)

        self.dialog.wait_window()

    def copy_to_clipboard(self):
        try:
            pyperclip.copy(self.text)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy: {e}")

    def save_to_file(self):
        path = filedialog.asksaveasfilename(
            title="Save Extracted Text",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(self.text)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")
```

**Step 2: Smoke-test via REPL**

Run:
```
python -c "import tkinter as tk; from screensnap import OCRResultDialog; root = tk.Tk(); root.withdraw(); OCRResultDialog(root, 'hello world\nline two', copied=True)"
```
Expected: A dialog appears showing the two-line text and status `Copied 20 characters to clipboard`. Click COPY — paste into Notepad should yield the exact text. Click SAVE AS .TXT — file should write. Click CLOSE — dialog dismisses and script exits.

Then test the empty case:
```
python -c "import tkinter as tk; from screensnap import OCRResultDialog; root = tk.Tk(); root.withdraw(); OCRResultDialog(root, '')"
```
Expected: Dialog shows `No text detected.`, only a CLOSE button (no Copy / Save).

**Step 3: Commit**

```bash
git add screensnap.py
git commit -m "feat(ocr): add OCRResultDialog for previewing extracted text"
```

---

## Task 6: Wire up editor **OCR** button

**Files:**
- Modify: `screensnap.py:2129-2138` (actions toolbar in `AnnotationEditor._build_toolbar`)
- Modify: `screensnap.py` — add new method on `AnnotationEditor` near `copy_image_to_clipboard` (line ~5022)

**Step 1: Add the `ocr_current_image` method**

Insert immediately **after** `copy_image_to_clipboard` (ends around line 5057):

```python
    def ocr_current_image(self):
        """Extract text from current image via Tesseract and show preview dialog."""
        # Bake annotations into self.image, matching Copy Image / Save behavior.
        self.render_annotations_to_image()

        self.status_var.set("Running OCR...")
        self.root.config(cursor="watch")
        self.root.update()
        try:
            text = run_ocr(self.image.copy(), self.settings)
        except TesseractNotFoundError:
            self.root.config(cursor="")
            self.status_var.set("OCR failed: Tesseract not found")
            self._prompt_install_tesseract()
            return
        except Exception as e:
            self.root.config(cursor="")
            self.status_var.set(f"OCR failed: {e}")
            messagebox.showerror("OCR Error", f"Tesseract failed:\n{e}")
            return
        finally:
            self.root.config(cursor="")

        copied = False
        if text:
            try:
                pyperclip.copy(text)
                copied = True
            except Exception:
                pass
            self.status_var.set(f"OCR: extracted {len(text)} characters")
        else:
            self.status_var.set("OCR: no text detected")

        OCRResultDialog(self.root, text, copied=copied)

    def _prompt_install_tesseract(self):
        """Show an error dialog with install link and Browse fallback."""
        INSTALL_URL = "https://github.com/UB-Mannheim/tesseract/wiki"
        answer = messagebox.askyesno(
            "Tesseract Not Installed",
            "Tesseract is required for OCR but was not found on this machine.\n\n"
            f"Install it from:\n{INSTALL_URL}\n\n"
            "Would you like to browse for an existing tesseract.exe now?"
        )
        if not answer:
            try:
                os.startfile(INSTALL_URL)
            except Exception:
                pass
            return

        path = filedialog.askopenfilename(
            title="Select tesseract.exe",
            filetypes=[("tesseract.exe", "tesseract.exe"), ("All files", "*.*")],
        )
        if path and os.path.isfile(path):
            self.settings['tesseract_path'] = path
            SettingsManager.save(self.settings)
            # Retry
            self.ocr_current_image()
```

**Step 2: Add the OCR toolbar button**

In `_build_toolbar`, in the actions_frame block (around line 2135), insert the OCR button **between** COPY IMAGE and SAVE & COPY:

```python
        ModernButton(actions_frame, text="🔤 OCR", variant="primary", command=self.ocr_current_image).pack(side='right', padx=5)
```

Order after edit should be: `SHARE`, `SAVE & COPY`, `OCR`, `COPY IMAGE`, `REGION`, `LAUNCHER` (right-packed, so SHARE ends up leftmost).

**Step 3: Smoke-test**

Run: `screensnap.bat` → full screen capture → editor opens.

Test 1 — happy path (assumes Tesseract is installed):
Click **OCR** button. Status shows `Running OCR...`. A preview dialog appears with extracted text from your screen. Paste into Notepad — matches the dialog text.

Test 2 — empty image:
Open a fresh editor with a mostly-blank region (region capture of a white area). Click OCR. Dialog shows `No text detected.`

Test 3 — missing Tesseract (if testable):
Temporarily set `tesseract_path` in `settings.ini` to a bogus path like `C:\nope.exe` AND rename `C:\Program Files\Tesseract-OCR` if installed. Click OCR. Expect the "Tesseract Not Installed" prompt with Browse option.

**Step 4: Commit**

```bash
git add screensnap.py
git commit -m "feat(ocr): add OCR button to annotation editor toolbar"
```

---

## Task 7: Add launcher **Capture Text** button and handler

**Files:**
- Modify: `screensnap.py:705-722` (launcher capture buttons block)
- Modify: `screensnap.py` — add new method on `LauncherWindow` near `execute_region_capture` (line ~1084)

**Step 1: Add the launcher button**

In `LauncherWindow.__init__`, immediately **after** the `region_btn.pack(fill='x', pady=8)` line (around line 722), add:

```python
        text_btn = ModernButton(
            main_container,
            variant="action",
            text="🔤  CAPTURE TEXT",
            command=self.capture_text,
            font=("Segoe UI Bold", 11)
        )
        text_btn.pack(fill='x', pady=8)
```

**Step 2: Add `capture_text` method**

Insert immediately **after** `execute_region_capture` (ends around line 1112):

```python
    def capture_text(self):
        """Capture a region → run OCR → show preview. Editor is skipped."""
        self.root.withdraw()
        self.root.after(200, self._execute_text_capture)

    def _execute_text_capture(self):
        try:
            selector = RegionSelector(self.root)
            if selector.result:
                self.root.config(cursor="watch")
                self.root.update()
                try:
                    text = run_ocr(selector.result, self.settings)
                except TesseractNotFoundError:
                    self.root.config(cursor="")
                    self._prompt_install_tesseract_launcher()
                    return
                except Exception as e:
                    self.root.config(cursor="")
                    messagebox.showerror("OCR Error", f"Tesseract failed:\n{e}")
                    return
                finally:
                    self.root.config(cursor="")

                copied = False
                if text:
                    try:
                        pyperclip.copy(text)
                        copied = True
                    except Exception:
                        pass
                OCRResultDialog(self.root, text, copied=copied)
        except Exception as e:
            messagebox.showerror("Error", f"Text capture failed: {e}")
        finally:
            _clear_root(self.root)
            self.root.deiconify()
            self._build_launcher_ui()

    def _prompt_install_tesseract_launcher(self):
        """Tesseract-missing prompt from the launcher context."""
        INSTALL_URL = "https://github.com/UB-Mannheim/tesseract/wiki"
        answer = messagebox.askyesno(
            "Tesseract Not Installed",
            "Tesseract is required for OCR but was not found on this machine.\n\n"
            f"Install it from:\n{INSTALL_URL}\n\n"
            "Would you like to browse for an existing tesseract.exe now?"
        )
        if not answer:
            try:
                os.startfile(INSTALL_URL)
            except Exception:
                pass
            return
        path = filedialog.askopenfilename(
            title="Select tesseract.exe",
            filetypes=[("tesseract.exe", "tesseract.exe"), ("All files", "*.*")],
        )
        if path and os.path.isfile(path):
            self.settings['tesseract_path'] = path
            SettingsManager.save(self.settings)
```

**Note on the `_build_launcher_ui` call:** `LauncherWindow` uses an inline UI rebuild in `__init__`, not a named method — but `execute_region_capture` already calls `self._build_launcher_ui()` (line ~1107), so that helper must already exist. Verify it exists before shipping this task; if it does not, model `capture_text` on the same rebuild flow that `execute_region_capture` uses (search for `_build_launcher_ui` in `LauncherWindow` first and mirror its pattern).

**Step 3: Smoke-test**

Run: `screensnap.bat` → Launcher opens → click **CAPTURE TEXT**.
Expected: launcher hides, region selector overlay appears. Drag over a region containing text. Preview dialog appears with extracted text, and the text is already in the clipboard. Close — launcher returns.

Test 2 — cancel region:
Click **CAPTURE TEXT**, then press Esc in the region selector. Expected: launcher reappears, no dialog, no errors.

Test 3 — blank region:
Click **CAPTURE TEXT**, drag a blank/solid-color region. Expected: dialog shows `No text detected.` — clipboard unchanged.

**Step 4: Commit**

```bash
git add screensnap.py
git commit -m "feat(ocr): add Capture Text button to launcher"
```

---

## Task 8: Update activity log

**Files:**
- Modify (or create): `process/activity-log.md`

**Step 1: Add entry**

Per the global instructions in `CLAUDE.md`, add an entry at the top of `process/activity-log.md` under a `## 2026-04-22` heading:

```markdown
### Image-to-Text OCR
**Files Changed:** `screensnap.py`, `docs/plans/2026-04-22-image-to-text-ocr-design.md`, `docs/plans/2026-04-22-image-to-text-ocr.md`

- Added Tesseract-backed OCR with two entry points: `OCR` button in the editor toolbar, and `CAPTURE TEXT` button on the launcher.
- Extracted text auto-copies to clipboard and opens in a new `OCRResultDialog` with Copy / Save as .txt / Close actions.
- Added optional `tesseract_path` setting with auto-discovery fallback (common install dirs + PATH).
- `pytesseract` added to `ensure_dependencies()` for first-run auto-install.

**Deployment:** Not deployed
```

If an entry for 2026-04-22 already exists, append under the same date with `---` separator.

**Step 2: Commit**

```bash
git add process/activity-log.md
git commit -m "docs: log OCR feature in activity log"
```

---

## Task 9: Final end-to-end verification

No code changes. Walk the manual test checklist from the design doc:

- [ ] Editor **OCR** button extracts text from a screenshot with visible text; dialog opens with correct character count; clipboard content matches.
- [ ] Editor **OCR** with a text annotation + step annotation overlaid — annotations appear in OCR output (expected behavior).
- [ ] Launcher **CAPTURE TEXT** → region selector → preview dialog; editor is not shown.
- [ ] Launcher **CAPTURE TEXT** → Esc in selector → launcher returns cleanly, no dialog.
- [ ] Settings **Tesseract path** + Browse writes to `settings.ini`; next OCR uses it.
- [ ] With Tesseract missing (simulate via bogus path + no install), OCR shows the install prompt with working Browse fallback.
- [ ] Empty/blank capture → `No text detected.` dialog, clipboard untouched.
- [ ] Save as .txt produces a readable UTF-8 file.

If any box fails, file a follow-up task and fix before marking the feature done.
