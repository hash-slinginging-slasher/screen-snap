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
