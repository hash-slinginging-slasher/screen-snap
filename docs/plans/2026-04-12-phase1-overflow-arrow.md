# Phase 1: Overflow Menu + Arrow Tool — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a "More ▾" overflow dropdown to the annotation toolbar and implement the Arrow tool as the first new annotation tool.

**Architecture:** Extends the existing single-file `screensnap.py`. The overflow menu is a `tk.Menubutton` with a `tk.Menu` dropdown placed after the Step button. The Arrow tool uses eager rendering (same as rectangle/line/circle) — drawn into `self.image` via `ImageDraw` on mouse release. Arrow properties panel follows the same show/hide pattern as text/step panels.

**Tech Stack:** tkinter (tk.Menubutton, tk.Menu), Pillow (ImageDraw.polygon, ImageDraw.line), existing ModernButton/Theme system.

**Design doc:** `docs/plans/2026-04-12-annotation-tools-design.md`

---

### Task 1: Add the "More ▾" overflow button to the toolbar

**Files:**
- Modify: `screensnap.py` — `create_toolbar()` (~line 1806), `set_tool()` (~line 1920)

**Step 1: Add the overflow Menubutton after the tool buttons loop**

In `create_toolbar()`, after the tools loop (line 1831), add a `tk.Menubutton` styled to match `ModernButton`. Insert it before the separator `tk.Frame(toolbar, width=1, ...)` at line 1833.

```python
        # Overflow "More" dropdown for additional tools
        self.overflow_menu_btn = tk.Menubutton(
            tools_frame,
            text="More ▾",
            font=Theme.FONT_BUTTON,
            bg=Theme.SURFACE,
            fg=Theme.ON_SURFACE_VARIANT,
            activebackground=Theme.SURFACE_BRIGHT,
            activeforeground=Theme.ON_SURFACE,
            relief='flat',
            borderwidth=0,
            cursor='hand2',
            padx=15,
            pady=5,
        )
        self.overflow_menu_btn.pack(side='left', padx=2)

        self.overflow_menu = tk.Menu(
            self.overflow_menu_btn,
            tearoff=0,
            bg=Theme.SURFACE,
            fg=Theme.ON_SURFACE,
            activebackground=Theme.PRIMARY,
            activeforeground="#000000",
            font=Theme.FONT_BUTTON,
            borderwidth=1,
            relief='flat',
        )
        self.overflow_menu_btn['menu'] = self.overflow_menu

        # All overflow tools — only Arrow is functional in Phase 1
        self.overflow_tools = [
            ('Arrow', 'arrow', 'A'),
            ('Stamp', 'stamp', 'M'),
            ('Bubble', 'bubble', 'B'),
            ('Smart Move', 'smart_move', 'V'),
            ('Blur', 'blur', 'U'),
            ('Highlight', 'highlight', 'H'),
        ]
        self._overflow_tool_names = {t[1] for t in self.overflow_tools}
        self._implemented_overflow = {'arrow'}  # Phase 1: only arrow works

        for label, tool, key in self.overflow_tools:
            if tool in self._implemented_overflow:
                self.overflow_menu.add_command(
                    label=f"{label} ({key})",
                    command=lambda t=tool: self.set_tool(t),
                )
            else:
                self.overflow_menu.add_command(
                    label=f"{label} ({key}) — Coming soon",
                    state='disabled',
                )
```

**Step 2: Update `set_tool()` to handle overflow tools**

In `set_tool()` (~line 1920), extend the button-state loop and add overflow label updating:

```python
    def set_tool(self, tool):
        """Set the current drawing tool with Midnight Architect styling."""
        self.current_tool = tool
        self.status_var.set(f"MODE: {tool.upper()}")

        # Update primary button states (Capsule highlight)
        for t in ['rectangle', 'line', 'circle', 'crop', 'text', 'step']:
            btn = getattr(self, f'{t}_btn', None)
            if btn:
                if t == tool:
                    btn.config(bg=Theme.PRIMARY, fg="#000000")
                else:
                    btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)

        # Update overflow menu button label
        if tool in self._overflow_tool_names:
            # Show active overflow tool name on the button
            display = next(
                (lbl for lbl, t, _ in self.overflow_tools if t == tool),
                tool.title()
            )
            self.overflow_menu_btn.config(
                text=f"{display} ▾",
                bg=Theme.PRIMARY,
                fg="#000000",
            )
        else:
            self.overflow_menu_btn.config(
                text="More ▾",
                bg=Theme.SURFACE,
                fg=Theme.ON_SURFACE_VARIANT,
            )

        # Show/hide properties panels
        if tool == 'text':
            self.text_props_frame.pack(side='top', fill='x')
            self.step_props_frame.pack_forget()
            self.arrow_props_frame.pack_forget()
        elif tool == 'step':
            self.step_props_frame.pack(side='top', fill='x')
            self.text_props_frame.pack_forget()
            self.arrow_props_frame.pack_forget()
        elif tool == 'arrow':
            self.arrow_props_frame.pack(side='top', fill='x')
            self.text_props_frame.pack_forget()
            self.step_props_frame.pack_forget()
        else:
            self.text_props_frame.pack_forget()
            self.step_props_frame.pack_forget()
            self.arrow_props_frame.pack_forget()
            self.deselect_all()
```

**Step 3: Register keyboard shortcuts for overflow tools**

In the key-binding block (~line 1781), add bindings for all overflow tools:

```python
        # Overflow tool shortcuts
        for k, t in [('a','arrow'), ('m','stamp'), ('b','bubble'), ('v','smart_move'), ('u','blur'), ('h','highlight')]:
            if t in self._implemented_overflow:
                self.root.bind(f'<{k}>', lambda e, tool=t: self.set_tool(tool))
                self.root.bind(f'<{k.upper()}>', lambda e, tool=t: self.set_tool(tool))
            else:
                self.root.bind(f'<{k}>', lambda e, tool=t: self.status_var.set(f"{tool.upper()}: Coming soon"))
                self.root.bind(f'<{k.upper()}>', lambda e, tool=t: self.status_var.set(f"{tool.upper()}: Coming soon"))
```

**Step 4: Test manually**

Run: `screensnap.bat full`

Expected:
- "More ▾" button appears after Step in the toolbar
- Clicking it shows dropdown with "Arrow (A)" enabled, rest disabled/greyed
- Clicking Arrow changes button label to "Arrow ▾" with primary highlight
- Clicking any primary tool resets label to "More ▾"
- Press `A` key to activate Arrow tool
- Press `M`/`B`/`V`/`U`/`H` keys show "Coming soon" in status bar

**Step 5: Commit**

```bash
git add screensnap.py
git commit -m "feat: add overflow 'More' dropdown menu to annotation toolbar"
```

---

### Task 2: Add arrow properties panel

**Files:**
- Modify: `screensnap.py` — `__init__()` (~line 1586), after step_props_frame setup (~line 1723)

**Step 1: Add arrow state variables to `__init__()`**

After the step tool properties block (~line 1631), add:

```python
        # Arrow tool properties
        self.arrow_style = 'filled'     # 'filled' or 'open'
        self.arrow_heads = 'single'     # 'single' or 'double'
```

**Step 2: Create the arrow properties panel**

After the step_props_frame block (~line 1723) and before the canvas frame block (~line 1725), add:

```python
        # Arrow properties panel
        self.arrow_props_frame = tk.Frame(self.props_container, bg=Theme.SURFACE, padx=15, pady=10)
        self.arrow_props_frame.pack(side='top', fill='x')
        self.arrow_props_frame.pack_forget()

        tk.Label(self.arrow_props_frame, text="ARROW TOOL", font=("Segoe UI Bold", 8),
                 fg=Theme.PRIMARY, bg=Theme.SURFACE).pack(side='left', padx=(0, 20))

        tk.Label(self.arrow_props_frame, text="Style", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))

        self.arrow_filled_btn = ModernButton(
            self.arrow_props_frame, text="▶ Filled", variant="primary",
            command=lambda: self._set_arrow_style('filled'),
            font=("Segoe UI Bold", 8))
        self.arrow_filled_btn.pack(side='left', padx=2)

        self.arrow_open_btn = ModernButton(
            self.arrow_props_frame, text="▷ Open", variant="tool",
            command=lambda: self._set_arrow_style('open'),
            font=("Segoe UI Bold", 8))
        self.arrow_open_btn.pack(side='left', padx=(2, 20))

        tk.Label(self.arrow_props_frame, text="Heads", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))

        self.arrow_single_btn = ModernButton(
            self.arrow_props_frame, text="→ Single", variant="primary",
            command=lambda: self._set_arrow_heads('single'),
            font=("Segoe UI Bold", 8))
        self.arrow_single_btn.pack(side='left', padx=2)

        self.arrow_double_btn = ModernButton(
            self.arrow_props_frame, text="↔ Double", variant="tool",
            command=lambda: self._set_arrow_heads('double'),
            font=("Segoe UI Bold", 8))
        self.arrow_double_btn.pack(side='left', padx=2)
```

**Step 3: Add the toggle helper methods**

Add these methods near `set_tool()`:

```python
    def _set_arrow_style(self, style):
        """Toggle arrow style between filled and open."""
        self.arrow_style = style
        if style == 'filled':
            self.arrow_filled_btn.config(bg=Theme.PRIMARY, fg="#000000")
            self.arrow_open_btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)
        else:
            self.arrow_open_btn.config(bg=Theme.PRIMARY, fg="#000000")
            self.arrow_filled_btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)

    def _set_arrow_heads(self, heads):
        """Toggle arrow heads between single and double."""
        self.arrow_heads = heads
        if heads == 'single':
            self.arrow_single_btn.config(bg=Theme.PRIMARY, fg="#000000")
            self.arrow_double_btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)
        else:
            self.arrow_double_btn.config(bg=Theme.PRIMARY, fg="#000000")
            self.arrow_single_btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)
```

**Step 4: Test manually**

Run: `screensnap.bat full`

Expected:
- Select Arrow from overflow menu → arrow props panel appears
- Click Filled/Open → button highlight toggles correctly
- Click Single/Double → button highlight toggles correctly
- Select a primary tool → arrow props panel hides

**Step 5: Commit**

```bash
git add screensnap.py
git commit -m "feat: add arrow tool properties panel (style and heads toggles)"
```

---

### Task 3: Implement arrow drawing — canvas preview during drag

**Files:**
- Modify: `screensnap.py` — `on_canvas_drag()` (~line 2683)

**Step 1: Add arrow preview branch to `on_canvas_drag()`**

In the preview drawing section (after the step preview at ~line 2787, before the shape preview at ~line 2790), add an arrow preview:

```python
        # Draw preview for arrow tool
        if self.current_tool == 'arrow':
            # Main shaft line
            self.current_shape = self.canvas.create_line(
                self.start_x, self.start_y, x, y,
                fill=self.current_color,
                width=self.stroke_width,
                arrow='both' if self.arrow_heads == 'double' else 'last',
                arrowshape=(
                    self.stroke_width * 4,  # length
                    self.stroke_width * 3,  # width at base
                    self.stroke_width * 1,  # width at tip
                ),
            )
            return
```

**Step 2: Test manually**

Run: `screensnap.bat full`

Expected:
- Select Arrow tool, click and drag on canvas
- Arrow preview appears with arrowhead at cursor end
- Preview updates as mouse moves
- Preview disappears on release (no permanent drawing yet)
- Toggle to Double → preview shows heads on both ends

**Step 3: Commit**

```bash
git add screensnap.py
git commit -m "feat: add arrow canvas preview during drag"
```

---

### Task 4: Implement arrow drawing — commit to image on release

**Files:**
- Modify: `screensnap.py` — `on_canvas_release()` (~line 2817)

**Step 1: Add `_draw_arrow_on_image()` helper method**

Add this method near the other drawing helpers:

```python
    def _draw_arrow_on_image(self, draw, x1, y1, x2, y2, color, width, style, heads):
        """Draw an arrow with arrowhead(s) onto an ImageDraw context.

        Args:
            draw: ImageDraw.Draw instance
            x1, y1: start point (image coords)
            x2, y2: end point (image coords)
            color: fill color string
            width: line stroke width
            style: 'filled' or 'open'
            heads: 'single' or 'double'
        """
        import math

        # Draw the shaft
        draw.line([(x1, y1), (x2, y2)], fill=color, width=width)

        head_length = width * 4
        head_width = width * 3

        def _arrowhead(tip_x, tip_y, from_x, from_y):
            """Compute and draw one arrowhead pointing at (tip_x, tip_y)
            from the direction of (from_x, from_y)."""
            angle = math.atan2(tip_y - from_y, tip_x - from_x)
            # Two base points of the triangle
            lx = tip_x - head_length * math.cos(angle) + head_width * math.sin(angle) / 2
            ly = tip_y - head_length * math.sin(angle) - head_width * math.cos(angle) / 2
            rx = tip_x - head_length * math.cos(angle) - head_width * math.sin(angle) / 2
            ry = tip_y - head_length * math.sin(angle) + head_width * math.cos(angle) / 2

            if style == 'filled':
                draw.polygon([(tip_x, tip_y), (lx, ly), (rx, ry)], fill=color)
            else:
                draw.line([(lx, ly), (tip_x, tip_y)], fill=color, width=max(1, width // 2))
                draw.line([(rx, ry), (tip_x, tip_y)], fill=color, width=max(1, width // 2))

        # Head at the end (always)
        _arrowhead(x2, y2, x1, y1)

        # Head at the start (if double)
        if heads == 'double':
            _arrowhead(x1, y1, x2, y2)
```

**Step 2: Add the arrow case to `on_canvas_release()`**

In `on_canvas_release()`, after the `elif self.current_tool == 'circle':` block (~line 2878) and before the `elif self.current_tool == 'crop':` block (~line 2879), add:

```python
        elif self.current_tool == 'arrow':
            # Arrow uses start→end direction, NOT min/max bounds
            z = self.zoom if self.zoom else 1.0
            ax1, ay1 = self.start_x / z, self.start_y / z
            ax2, ay2 = x / z, y / z
            self._draw_arrow_on_image(
                draw, ax1, ay1, ax2, ay2,
                self.current_color, self.stroke_width,
                self.arrow_style, self.arrow_heads,
            )
            self.refresh_display()
            return
```

**Important:** The arrow tool needs the raw `start_x/start_y → x/y` directional coords, NOT the `min/max`-normalized `ix1/iy1/ix2/iy2` used by rectangle/circle. So we compute image coords from the raw start/end and return early, before the min-size check. Move the arrow check **above** the min-size check and bounds calculation block, or use the raw coords directly.

Actually, the better approach: insert the arrow handling right after `self.save_state()` (line 2851) but **before** the `ix1/iy1/ix2/iy2` calculation. This way it uses `self.start_x/self.start_y` and `x/y` (canvas coords) and does its own zoom conversion:

```python
        # Arrow tool — uses directional start→end, not normalized bounds
        if self.current_tool == 'arrow':
            z = self.zoom if self.zoom else 1.0
            ax1, ay1 = self.start_x / z, self.start_y / z
            ax2, ay2 = x / z, y / z
            draw = ImageDraw.Draw(self.image)
            self._draw_arrow_on_image(
                draw, ax1, ay1, ax2, ay2,
                self.current_color, self.stroke_width,
                self.arrow_style, self.arrow_heads,
            )
            self.refresh_display()
            return
```

**Step 3: Test manually**

Run: `screensnap.bat full`

Expected:
- Select Arrow, drag on canvas → arrow drawn with filled arrowhead at end
- Toggle to Open → arrowhead is two lines instead of filled triangle
- Toggle to Double → arrowheads on both ends
- Ctrl+Z undoes the arrow
- Arrow respects current color and stroke width
- Arrow works at different zoom levels

**Step 4: Commit**

```bash
git add screensnap.py
git commit -m "feat: implement arrow tool rendering on image with filled/open and single/double heads"
```

---

### Task 5: Wire up the minimum-size guard for arrow

**Files:**
- Modify: `screensnap.py` — `on_canvas_release()` (~line 2847)

**Step 1: Adjust the min-size check to allow arrows through**

The existing min-size check (line 2847) uses `x2 - x1 < 5 or y2 - y1 < 5` which blocks diagonal arrows. Since the arrow handler is inserted before the bounds calculation, this is already handled — the arrow returns early before that check.

However, we need to add a separate min-length check in the arrow handler itself to prevent zero-length arrows:

```python
        if self.current_tool == 'arrow':
            z = self.zoom if self.zoom else 1.0
            ax1, ay1 = self.start_x / z, self.start_y / z
            ax2, ay2 = x / z, y / z
            # Skip if arrow is too short
            length = math.hypot(ax2 - ax1, ay2 - ay1)
            if length < 5:
                return
            draw = ImageDraw.Draw(self.image)
            ...
```

This is incorporated into Task 4's code. **No separate step needed** — just verify during Task 4 testing that very short clicks don't produce artifacts.

---

### Task 6: Final integration test and cleanup

**Files:**
- Modify: `screensnap.py` (if any issues found)

**Step 1: Full integration test**

Run: `screensnap.bat full`

Test checklist:
- [ ] "More ▾" dropdown appears and opens correctly
- [ ] Arrow (A) activates from dropdown and keyboard shortcut
- [ ] Arrow properties panel shows with Style and Heads toggles
- [ ] Filled triangle arrowhead renders correctly
- [ ] Open triangle arrowhead renders correctly
- [ ] Single-head arrow renders correctly
- [ ] Double-head arrow renders correctly
- [ ] Arrow respects selected color from palette
- [ ] Arrow respects stroke width setting
- [ ] Canvas preview shows during drag
- [ ] Undo (Ctrl+Z) removes the arrow
- [ ] Redo (Ctrl+Y) restores the arrow
- [ ] Arrow works at zoom != 1.0
- [ ] Switching from Arrow to primary tool resets "More ▾" label
- [ ] Disabled overflow tools show "Coming soon" in status bar
- [ ] Save & Copy includes arrows in the output image
- [ ] All existing tools still work (rectangle, line, circle, crop, text, step)

**Step 2: Commit final state**

```bash
git add screensnap.py
git commit -m "feat: complete Phase 1 — overflow menu and arrow annotation tool"
```

---

## Summary of changes to `screensnap.py`

| Location | Change |
|---|---|
| `__init__()` ~line 1631 | Add `arrow_style`, `arrow_heads` state vars |
| After step_props_frame ~line 1723 | Add `arrow_props_frame` with style/heads toggles |
| `create_toolbar()` ~line 1831 | Add `overflow_menu_btn` + `overflow_menu` with 6 tool entries |
| Key bindings ~line 1781 | Add A/M/B/V/U/H shortcuts |
| `set_tool()` ~line 1920 | Handle overflow tool names, update menu button label, show/hide arrow props |
| `on_canvas_drag()` ~line 2787 | Add arrow preview with `create_line(arrow=...)` |
| `on_canvas_release()` ~line 2851 | Add arrow case before bounds normalization; call `_draw_arrow_on_image()` |
| New method | `_draw_arrow_on_image()` — renders arrow shaft + arrowhead(s) via ImageDraw |
| New method | `_set_arrow_style()` — toggle filled/open button highlight |
| New method | `_set_arrow_heads()` — toggle single/double button highlight |
