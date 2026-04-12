## 2026-04-12

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
