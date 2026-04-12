# Annotation Tools Expansion — Design Document

**Date:** 2026-04-12
**Status:** Approved
**Approach:** Phase-based (Approach C)

## Summary

Add 6 new annotation tools to ScreenSnap via a toolbar overflow dropdown menu. Built in two phases: Phase 1 validates the overflow UI pattern with the Arrow tool, Phase 2 adds the remaining tools incrementally.

## Priority Order

1. Arrow (Phase 1)
2. Stamp Library (Phase 2)
3. Speech Bubbles (Phase 2)
4. Smart Move (Phase 2)
5. Blur/Pixelate (Phase 2)
6. Highlight (Phase 2)

---

## Toolbar: Overflow Menu

**Current toolbar:** `Rectangle (R) | Line (L) | Circle (C) | Crop (X) | Text (T) | Step (P)`

The existing 6 primary tools remain visible. A **"More ▾"** button is added after Step, opening a `tk.Menu` dropdown with all 6 new tools.

**Behavior:**
- Selecting a tool from the dropdown changes the More button label to the active tool name (e.g., `"Arrow ▾"`) with active highlight styling
- Selecting any primary tool resets the label to `"More ▾"`
- Keyboard shortcuts work globally: A (Arrow), M (Stamp), B (Bubble), V (Smart Move), U (Blur), H (Highlight)

---

## Tool 1: Arrow (Shortcut: A)

**Rendering:** Eager — drawn into `self.image` via `ImageDraw` on mouse release (same as shape tools).

### Interaction
- Click and drag to draw. Line starts at mouse-down, arrowhead at mouse-up end.
- Canvas preview line shown during drag (like existing line tool).
- After release, arrow is committed to `self.image`.
- Double-click a placed arrow to add a text label along the shaft (small entry widget at midpoint, Enter to commit).

### Arrowhead Options (properties panel)
- **Style:** Filled triangle (default) or Open triangle — toggled via buttons
- **Heads:** Single-head (default) or Double-head — toggled via button

### Rendering Details
- Head size scales with stroke width: `head_length = stroke_width * 4`, `head_width = stroke_width * 3`
- Filled triangle: `ImageDraw.polygon()` with 3-point polygon
- Open triangle: two lines from tip via `ImageDraw.line()`
- Text label: same font system as text tool, centered at midpoint, semi-transparent background pill for readability

---

## Tool 2: Stamp Library (Shortcut: M)

**Rendering:** Eager — composited into `self.image` on placement using 4x supersampled tiles (same technique as step tool).

### Interaction
- Properties panel shows a scrollable grid of stamp previews organized by category
- Click on canvas to place the selected stamp at that position
- Stamp size adjustable via slider in properties panel

### Stamp Set (~20+ vector icons)

All drawn programmatically with `ImageDraw` (polygons, arcs, lines). Each stamp is a function: `(draw, x, y, size, color) -> None`.

| Category | Icons |
|---|---|
| Status | checkmark, X/cross, warning triangle, info circle, question mark |
| Reaction | thumbs up, thumbs down, heart, star |
| Technical | bug, lock, unlock, lightbulb, gear |
| Indicators | numbered badges (1-9), arrow pointer, cloud, fire |
| Emoji-style | happy face, sad face, neutral face |

### Rendering Details
- 4x supersample + LANCZOS downsample for crisp edges
- Drop shadow behind each stamp (same approach as step tool)
- Stamps use the current selected color from the palette

---

## Tool 3: Speech Bubbles / Modern Callout (Shortcut: B)

**Rendering:** Deferred — stays as canvas items while editable, burned into `self.image` on save via `render_bubbles_to_image()` (same pattern as text tool).

### Interaction
1. Click on canvas to place anchor point (the thing being annotated)
2. Rounded rectangle appears offset from click with thin connector line
3. Bubble immediately enters text-editing mode — user types annotation
4. Escape or click outside to finish editing
5. Double-click to re-edit text
6. Drag bubble body to reposition; drag anchor point to change connector target

### Visual Style
- Rounded rectangle: `corner_radius = 8`, filled with `current_color` at ~80% opacity, 1px border
- Connector: thin line (1.5px) from closest edge of rectangle to anchor point
- Small circle dot at anchor end of connector
- Text uses same font system as text tool

### Data Structure
```python
self.bubble_elements = [
    {
        "x": int, "y": int,           # bubble position
        "anchor_x": int, "anchor_y": int,  # connector target
        "text": str,
        "color": str,
        "font_size": int,
        "canvas_ids": {}               # shadow_id, bg_id, text_id, line_id, anchor_id
    }
]
```

### Properties Panel
Font size slider (reuses text tool's font size range).

---

## Tool 4: Smart Move (Shortcut: V)

**Rendering:** Immediate — modifies `self.image` directly, pushes to undo history.

### Interaction
1. Click and drag to select a rectangular region (crop-like selection UI)
2. Dashed border indicates the region is "picked up"
3. Drag selection to new position
4. On release: copies selected pixels to new position, fills vacated area

### Fill Algorithm (Clone-Stamp)
- Sample a border strip (8-16px) around the vacated rectangle from all four edges
- Extend border pixels inward using linear interpolation/blending
- Blend edge fills at corners where they meet
- Works well for solid colors, gradients, simple backgrounds. Complex textures may show artifacts — acceptable trade-off for zero dependencies.

### Properties Panel
None needed.

---

## Tool 5: Blur/Pixelate (Shortcut: U)

**Rendering:** Eager — applied to `self.image` on mouse release (same as shape tools).

### Interaction
- Click and drag to select rectangular area (crop-like selection)
- On release, selected region is blurred or pixelated and committed

### Modes (toggled in properties panel)
- **Pixelate:** Downscale region to small blocks via `Image.resize(NEAREST)`, then upscale back. `block_size` range: 5-30px.
- **Gaussian Blur:** Apply `ImageFilter.GaussianBlur(radius)` to region. `blur_radius` range: 5-25.

### Properties Panel
- Mode toggle: Pixelate / Blur (two buttons)
- Intensity slider: controls block_size or blur_radius depending on mode

---

## Tool 6: Highlight (Shortcut: H)

**Rendering:** Eager — composites semi-transparent overlay onto `self.image` on mouse release.

### Interaction
- Click and drag to draw rectangular highlight area
- On release, semi-transparent color fill applied to region

### Rendering
- Create temporary RGBA image sized to selection
- Fill with `current_color` at ~35% opacity
- Composite onto `self.image` via `Image.alpha_composite()` or `Image.paste()` with mask

### Properties Panel
None — uses existing color palette.

---

## Phase Structure

### Phase 1: Overflow Menu + Arrow Tool
- Add "More ▾" button to toolbar
- Implement dropdown with all 6 new tool names (only Arrow functional; rest show "Coming soon" in status bar)
- Build Arrow tool with full properties panel
- Register keyboard shortcuts for all new tools

### Phase 2: Remaining Tools (in priority order)
1. Stamp Library
2. Speech Bubbles
3. Smart Move
4. Blur/Pixelate
5. Highlight

Each tool is standalone — no cross-dependencies. Built and shipped independently.

## Architecture Notes

- All code stays in `screensnap.py` (single-file design)
- New tools follow existing patterns: eager rendering for shapes/stamps/blur/highlight, deferred for bubbles
- Properties panels use the same show/hide pattern as text and step tool panels
- `set_tool()` updated to handle all new tool names
- Undo history works as-is for eager-rendered tools (push `self.image.copy()` before commit)
- Bubble undo follows text tool pattern (canvas item removal + element list management)
