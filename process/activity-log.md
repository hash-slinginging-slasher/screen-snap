## 2026-04-12

### Implement arrow tool preview and rendering
**Files Changed:** `screensnap.py`

- Added arrow canvas preview during drag in `on_canvas_drag()` using `canvas.create_line()` with arrowheads
- Preview respects arrow_heads (single/double) and stroke_width for arrowshape proportions
- Added `_draw_arrow_on_image()` method for rendering arrows with filled or open arrowheads using trigonometry
- Added arrow commit logic in `on_canvas_release()` using directional coords (not normalized bounds)
- Arrow uses `math.hypot` for minimum length check (5px) instead of bounding-box size check

**Deployment:** Not deployed

---

### Revert unplanned features from toolbar commit
**Files Changed:** `screensnap.py`

- Reverted RGBA image loading change back to simple RGB conversion
- Removed "REMOVE BG" button from toolbar actions
- Removed `_make_checkerboard()` static method
- Removed RGBA checkerboard compositing in `refresh_display()`
- Removed `remove_background()`, `_remove_bg_color()`, and `_remove_bg_ai()` methods (~154 lines)
- Reverted RGBA save handling back to simple `self.image.save(file_path)`
- Amended the commit to keep only planned overflow menu and arrow properties changes

**Deployment:** Not deployed

---

### Add overflow menu and arrow properties panel to toolbar
**Files Changed:** `screensnap.py`

- Added "More" overflow dropdown button after primary tools in toolbar with 6 future tools (Arrow, Stamp, Bubble, Smart Move, Blur, Highlight)
- Arrow tool is enabled; remaining 5 show "Coming soon" and are disabled
- Added keyboard shortcuts for all overflow tools (A/M/B/V/U/H)
- Added arrow properties panel with Style (Filled/Open) and Heads (Single/Double) toggle buttons
- Updated set_tool() to handle overflow tool highlighting and arrow properties panel visibility
- Added arrow_style and arrow_heads state properties to AnnotationEditor

**Deployment:** Not deployed

---

### Add Annotation Tools Expansion Design Doc
**Files Changed:** `docs/plans/2026-04-12-annotation-tools-design.md`

- Brainstormed and designed 6 new annotation tools: Arrow, Stamp Library, Speech Bubbles, Smart Move, Blur/Pixelate, Highlight
- Chose phased approach: Phase 1 (overflow menu + Arrow), Phase 2 (remaining tools in priority order)
- Toolbar uses overflow dropdown to avoid clutter
- All tools stay in single-file architecture

**Deployment:** Not deployed
