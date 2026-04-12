## 2026-04-12

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
