# Phase 2: Remaining Annotation Tools — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 5 remaining annotation tools (Highlight, Blur/Pixelate, Stamp Library, Speech Bubbles, Smart Move) to the overflow menu.

**Architecture:** Each tool is standalone — no cross-dependencies. All code stays in `screensnap.py`. Eager-rendered tools (Highlight, Blur, Stamp, Smart Move) draw into `self.image` on mouse release. Speech Bubbles use deferred rendering (canvas items until save). Each tool enables its entry in `self._implemented_overflow` and optionally adds a properties panel.

**Tech Stack:** tkinter, Pillow (ImageDraw, ImageFilter, Image.resize), existing Theme/ModernButton system.

**Design doc:** `docs/plans/2026-04-12-annotation-tools-design.md`

---

## Key integration points (all tools share these)

### Enabling a tool in the overflow menu
In `create_toolbar()` at line ~1923, add the tool name to:
```python
self._implemented_overflow = {'arrow', '<new_tool>'}
```

### Adding properties panel show/hide
In `set_tool()` at line ~2056, add `elif tool == '<name>':` branch and add `.pack_forget()` calls to all other branches.

### Adding canvas preview
In `on_canvas_drag()` at line ~2861, add preview branch in the preview section.

### Adding image commit
In `on_canvas_release()` at line ~3010, add commit branch. For tools using normalized bounds (ix1/iy1/ix2/iy2), add after the existing shape cases. For directional tools, add before bounds normalization (like arrow).

---

### Task 1: Highlight Tool (Shortcut: H)

The simplest tool — semi-transparent color overlay on a rectangular region.

**Files:**
- Modify: `screensnap.py`

**Step 1: Enable highlight in overflow menu**

In `create_toolbar()` line ~1923, change:
```python
self._implemented_overflow = {'arrow', 'highlight'}
```

**Step 2: Add canvas preview in `on_canvas_drag()`**

After the arrow preview block (line ~2982) and before the rectangle/circle preview:
```python
        # Draw preview for highlight tool
        if self.current_tool == 'highlight':
            self.current_shape = self.canvas.create_rectangle(
                self.start_x, self.start_y, x, y,
                outline=self.current_color,
                fill=self.current_color,
                stipple='gray25',
                width=1,
            )
            return
```

**Step 3: Add commit in `on_canvas_release()`**

After the crop case (line ~3094) and before `self.refresh_display()`:
```python
        elif self.current_tool == 'highlight':
            # Semi-transparent color overlay at ~35% opacity
            region = self.image.crop((int(ix1), int(iy1), int(ix2), int(iy2)))
            overlay = Image.new('RGBA', region.size, self.current_color)
            # Set alpha to ~35%
            overlay.putalpha(89)
            # Composite: convert region to RGBA, paste overlay, convert back
            if region.mode != 'RGBA':
                region = region.convert('RGBA')
            region = Image.alpha_composite(region, overlay)
            self.image.paste(region.convert('RGB'), (int(ix1), int(iy1)))
```

**Step 4: Verify syntax**
```bash
python -c "import py_compile; py_compile.compile('screensnap.py', doraise=True)"
```

**Step 5: Commit**
```bash
git add screensnap.py
git commit -m "feat: add highlight annotation tool"
```

---

### Task 2: Blur/Pixelate Tool (Shortcut: U)

Rectangular selection that applies pixelation or Gaussian blur.

**Files:**
- Modify: `screensnap.py`

**Step 1: Enable blur in overflow menu**

Add `'blur'` to `self._implemented_overflow`.

**Step 2: Add blur state variables to `__init__()`**

After arrow tool properties (line ~1635):
```python
        # Blur tool properties
        self.blur_mode = 'pixelate'    # 'pixelate' or 'gaussian'
        self.blur_intensity = 15       # block_size (pixelate) or radius (gaussian)
```

**Step 3: Add blur properties panel**

After the arrow_props_frame block (line ~1769) and before `# Canvas frame`:
```python
        # Blur properties panel
        self.blur_props_frame = tk.Frame(self.props_container, bg=Theme.SURFACE, padx=15, pady=10)
        self.blur_props_frame.pack(side='top', fill='x')
        self.blur_props_frame.pack_forget()

        tk.Label(self.blur_props_frame, text="BLUR TOOL", font=("Segoe UI Bold", 8),
                 fg=Theme.PRIMARY, bg=Theme.SURFACE).pack(side='left', padx=(0, 20))

        tk.Label(self.blur_props_frame, text="Mode", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))

        self.blur_pixelate_btn = ModernButton(
            self.blur_props_frame, text="▦ Pixelate", variant="primary",
            command=lambda: self._set_blur_mode('pixelate'),
            font=("Segoe UI Bold", 8))
        self.blur_pixelate_btn.pack(side='left', padx=2)

        self.blur_gaussian_btn = ModernButton(
            self.blur_props_frame, text="◌ Blur", variant="tool",
            command=lambda: self._set_blur_mode('gaussian'),
            font=("Segoe UI Bold", 8))
        self.blur_gaussian_btn.pack(side='left', padx=(2, 20))

        tk.Label(self.blur_props_frame, text="Intensity", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))
        self.blur_intensity_var = tk.IntVar(value=15)
        blur_slider = ttk.Scale(self.blur_props_frame, from_=5, to=30,
                                variable=self.blur_intensity_var, orient='horizontal', length=120,
                                command=lambda v: setattr(self, 'blur_intensity', int(float(v))))
        blur_slider.pack(side='left', padx=(0, 5))
        self.blur_intensity_label = tk.Label(self.blur_props_frame, text="15",
                                             font=Theme.FONT_LABEL, fg=Theme.ON_SURFACE_VARIANT,
                                             bg=Theme.SURFACE, width=3)
        self.blur_intensity_label.pack(side='left')
        self.blur_intensity_var.trace_add('write', lambda *_: self.blur_intensity_label.config(
            text=str(self.blur_intensity_var.get())))
```

**Step 4: Add blur mode toggle method**

After `_set_arrow_heads()`:
```python
    def _set_blur_mode(self, mode):
        """Toggle blur mode between pixelate and gaussian."""
        self.blur_mode = mode
        if mode == 'pixelate':
            self.blur_pixelate_btn.config(bg=Theme.PRIMARY, fg="#000000")
            self.blur_gaussian_btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)
        else:
            self.blur_gaussian_btn.config(bg=Theme.PRIMARY, fg="#000000")
            self.blur_pixelate_btn.config(bg=Theme.SURFACE, fg=Theme.ON_SURFACE_VARIANT)
```

**Step 5: Update `set_tool()` for blur props panel**

Add `self.blur_props_frame.pack_forget()` to ALL existing branches in the properties panel section (text, step, arrow, else). Add new branch:
```python
        elif tool == 'blur':
            self.blur_props_frame.pack(side='top', fill='x')
            self.text_props_frame.pack_forget()
            self.step_props_frame.pack_forget()
            self.arrow_props_frame.pack_forget()
```

**Step 6: Add canvas preview in `on_canvas_drag()`**

After the highlight preview (or arrow preview), add:
```python
        # Draw preview for blur tool
        if self.current_tool == 'blur':
            self.current_shape = self.canvas.create_rectangle(
                self.start_x, self.start_y, x, y,
                outline='#FF9800',
                width=2,
                dash=(5, 5),
            )
            return
```

**Step 7: Add commit in `on_canvas_release()`**

After the highlight case:
```python
        elif self.current_tool == 'blur':
            region = self.image.crop((int(ix1), int(iy1), int(ix2), int(iy2)))
            if self.blur_mode == 'pixelate':
                # Downscale to blocks, then upscale back
                bs = max(1, self.blur_intensity)
                small_w = max(1, region.width // bs)
                small_h = max(1, region.height // bs)
                region = region.resize((small_w, small_h), Image.NEAREST)
                region = region.resize((int(ix2) - int(ix1), int(iy2) - int(iy1)), Image.NEAREST)
            else:
                from PIL import ImageFilter
                region = region.filter(ImageFilter.GaussianBlur(radius=self.blur_intensity))
            self.image.paste(region, (int(ix1), int(iy1)))
```

**Step 8: Verify syntax and commit**
```bash
python -c "import py_compile; py_compile.compile('screensnap.py', doraise=True)"
git add screensnap.py
git commit -m "feat: add blur/pixelate annotation tool"
```

---

### Task 3: Stamp Library Tool (Shortcut: M)

Programmatically drawn vector icons placed on click. Uses 4x supersampled tiles (same technique as step tool).

**Files:**
- Modify: `screensnap.py`

**Step 1: Enable stamp in overflow menu**

Add `'stamp'` to `self._implemented_overflow`.

**Step 2: Add stamp state variables to `__init__()`**

After blur tool properties:
```python
        # Stamp tool properties
        self.stamp_category = 'status'
        self.stamp_selected = 'checkmark'
        self.stamp_size = 40
        self.stamp_elements = []  # Track for undo: [{'x':, 'y':, 'stamp':, 'size':, 'color':}]
```

**Step 3: Define stamp drawing functions**

Add a class-level dict of stamp functions. Each takes `(draw, cx, cy, size, color)` where cx/cy is center:

```python
    # ── Stamp Library ────────────────────────────────────────────────
    STAMP_CATEGORIES = {
        'status': ['checkmark', 'cross', 'warning', 'info', 'question'],
        'reaction': ['thumbs_up', 'heart', 'star'],
        'technical': ['bug', 'lock', 'lightbulb', 'gear'],
        'emoji': ['happy', 'sad', 'neutral'],
    }

    @staticmethod
    def _draw_stamp(draw, name, cx, cy, size, color):
        """Draw a named stamp icon centered at (cx, cy)."""
        r = size // 2  # radius
        s = size  # full size

        if name == 'checkmark':
            # Filled circle background + check mark
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
            # White checkmark
            lw = max(1, s // 8)
            draw.line([(cx - r*0.35, cy), (cx - r*0.05, cy + r*0.35)], fill='white', width=lw)
            draw.line([(cx - r*0.05, cy + r*0.35), (cx + r*0.4, cy - r*0.3)], fill='white', width=lw)

        elif name == 'cross':
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
            lw = max(1, s // 8)
            off = r * 0.35
            draw.line([(cx-off, cy-off), (cx+off, cy+off)], fill='white', width=lw)
            draw.line([(cx+off, cy-off), (cx-off, cy+off)], fill='white', width=lw)

        elif name == 'warning':
            # Triangle
            pts = [(cx, cy - r), (cx - r, cy + r), (cx + r, cy + r)]
            draw.polygon(pts, fill=color)
            lw = max(1, s // 10)
            draw.line([(cx, cy - r*0.2), (cx, cy + r*0.25)], fill='white', width=lw)
            draw.ellipse([cx - lw, cy + r*0.4 - lw, cx + lw, cy + r*0.4 + lw], fill='white')

        elif name == 'info':
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
            lw = max(1, s // 10)
            draw.ellipse([cx-lw, cy-r*0.5-lw, cx+lw, cy-r*0.5+lw], fill='white')
            draw.line([(cx, cy - r*0.15), (cx, cy + r*0.5)], fill='white', width=lw)

        elif name == 'question':
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
            lw = max(1, s // 10)
            # Simple ? using arc approximation
            draw.arc([cx-r*0.3, cy-r*0.6, cx+r*0.3, cy+r*0.05], 200, 440, fill='white', width=lw)
            draw.ellipse([cx-lw, cy+r*0.3-lw, cx+lw, cy+r*0.3+lw], fill='white')

        elif name == 'thumbs_up':
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
            # Simplified thumb shape
            lw = max(1, s // 8)
            draw.rectangle([cx-r*0.35, cy-r*0.1, cx+r*0.15, cy+r*0.5], fill='white')
            draw.ellipse([cx-r*0.15, cy-r*0.55, cx+r*0.25, cy-r*0.05], fill='white')

        elif name == 'heart':
            # Two circles + triangle for heart
            hr = r * 0.45
            draw.ellipse([cx - r*0.6, cy - r*0.4, cx, cy + r*0.15], fill=color)
            draw.ellipse([cx, cy - r*0.4, cx + r*0.6, cy + r*0.15], fill=color)
            draw.polygon([(cx - r*0.6, cy), (cx + r*0.6, cy), (cx, cy + r*0.7)], fill=color)

        elif name == 'star':
            # 5-point star
            pts = []
            for i in range(10):
                angle = math.radians(i * 36 - 90)
                rad = r if i % 2 == 0 else r * 0.4
                pts.append((cx + rad * math.cos(angle), cy + rad * math.sin(angle)))
            draw.polygon(pts, fill=color)

        elif name == 'bug':
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
            lw = max(1, s // 10)
            # Bug body: oval
            draw.ellipse([cx-r*0.3, cy-r*0.15, cx+r*0.3, cy+r*0.5], fill='white')
            # Bug head: small circle
            draw.ellipse([cx-r*0.15, cy-r*0.4, cx+r*0.15, cy-r*0.1], fill='white')
            # Antennae
            draw.line([(cx-r*0.1, cy-r*0.35), (cx-r*0.3, cy-r*0.55)], fill='white', width=lw)
            draw.line([(cx+r*0.1, cy-r*0.35), (cx+r*0.3, cy-r*0.55)], fill='white', width=lw)

        elif name == 'lock':
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
            # Lock body
            draw.rectangle([cx-r*0.3, cy-r*0.05, cx+r*0.3, cy+r*0.45], fill='white')
            # Lock shackle (arc)
            lw = max(1, s // 10)
            draw.arc([cx-r*0.2, cy-r*0.45, cx+r*0.2, cy+r*0.05], 180, 360, fill='white', width=lw)

        elif name == 'lightbulb':
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
            # Bulb
            draw.ellipse([cx-r*0.3, cy-r*0.5, cx+r*0.3, cy+r*0.15], fill='white')
            # Base
            lw = max(1, s // 10)
            draw.rectangle([cx-r*0.15, cy+r*0.15, cx+r*0.15, cy+r*0.35], fill='white')

        elif name == 'gear':
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
            # Gear: inner circle + teeth
            draw.ellipse([cx-r*0.25, cy-r*0.25, cx+r*0.25, cy+r*0.25], fill='white')
            lw = max(2, s // 8)
            for i in range(6):
                angle = math.radians(i * 60)
                dx, dy = r * 0.4 * math.cos(angle), r * 0.4 * math.sin(angle)
                draw.rectangle([cx+dx-lw//2, cy+dy-lw//2, cx+dx+lw//2, cy+dy+lw//2], fill='white')

        elif name == 'happy':
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
            ew = max(2, s // 10)
            draw.ellipse([cx-r*0.3-ew, cy-r*0.2-ew, cx-r*0.3+ew, cy-r*0.2+ew], fill='white')
            draw.ellipse([cx+r*0.3-ew, cy-r*0.2-ew, cx+r*0.3+ew, cy-r*0.2+ew], fill='white')
            draw.arc([cx-r*0.4, cy-r*0.1, cx+r*0.4, cy+r*0.45], 10, 170, fill='white', width=ew)

        elif name == 'sad':
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
            ew = max(2, s // 10)
            draw.ellipse([cx-r*0.3-ew, cy-r*0.2-ew, cx-r*0.3+ew, cy-r*0.2+ew], fill='white')
            draw.ellipse([cx+r*0.3-ew, cy-r*0.2-ew, cx+r*0.3+ew, cy-r*0.2+ew], fill='white')
            draw.arc([cx-r*0.4, cy+r*0.15, cx+r*0.4, cy+r*0.65], 190, 350, fill='white', width=ew)

        elif name == 'neutral':
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
            ew = max(2, s // 10)
            draw.ellipse([cx-r*0.3-ew, cy-r*0.2-ew, cx-r*0.3+ew, cy-r*0.2+ew], fill='white')
            draw.ellipse([cx+r*0.3-ew, cy-r*0.2-ew, cx+r*0.3+ew, cy-r*0.2+ew], fill='white')
            draw.line([(cx-r*0.3, cy+r*0.25), (cx+r*0.3, cy+r*0.25)], fill='white', width=ew)

        else:
            # Fallback: simple filled circle
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
```

**Step 4: Add stamp properties panel**

After blur_props_frame, add a panel with category selector, stamp grid, and size slider:
```python
        # Stamp properties panel
        self.stamp_props_frame = tk.Frame(self.props_container, bg=Theme.SURFACE, padx=15, pady=10)
        self.stamp_props_frame.pack(side='top', fill='x')
        self.stamp_props_frame.pack_forget()

        tk.Label(self.stamp_props_frame, text="STAMP TOOL", font=("Segoe UI Bold", 8),
                 fg=Theme.PRIMARY, bg=Theme.SURFACE).pack(side='left', padx=(0, 10))

        # Category selector
        tk.Label(self.stamp_props_frame, text="Category", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))
        self.stamp_category_var = tk.StringVar(value='status')
        cat_combo = ttk.Combobox(self.stamp_props_frame, textvariable=self.stamp_category_var,
                                 values=list(self.STAMP_CATEGORIES.keys()),
                                 state='readonly', width=10)
        cat_combo.pack(side='left', padx=(0, 10))
        cat_combo.bind('<<ComboboxSelected>>', lambda e: self._update_stamp_buttons())

        # Stamp buttons container
        self.stamp_btn_frame = tk.Frame(self.stamp_props_frame, bg=Theme.SURFACE)
        self.stamp_btn_frame.pack(side='left', padx=(0, 10))
        self._stamp_buttons = []
        self._update_stamp_buttons()

        # Size
        tk.Label(self.stamp_props_frame, text="Size", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))
        self.stamp_size_var = tk.IntVar(value=40)
        stamp_size_spin = ttk.Spinbox(self.stamp_props_frame, from_=20, to=120,
                                      textvariable=self.stamp_size_var, width=5,
                                      command=lambda: setattr(self, 'stamp_size', self.stamp_size_var.get()))
        stamp_size_spin.pack(side='left')
```

**Step 5: Add `_update_stamp_buttons()` and `_select_stamp()` methods**

```python
    def _update_stamp_buttons(self):
        """Rebuild stamp selection buttons for the current category."""
        for btn in self._stamp_buttons:
            btn.destroy()
        self._stamp_buttons.clear()

        category = self.stamp_category_var.get()
        stamps = self.STAMP_CATEGORIES.get(category, [])
        for name in stamps:
            display = name.replace('_', ' ').title()
            btn = ModernButton(
                self.stamp_btn_frame,
                text=display,
                variant="primary" if name == self.stamp_selected else "tool",
                command=lambda n=name: self._select_stamp(n),
                font=("Segoe UI Bold", 8),
            )
            btn.pack(side='left', padx=1)
            self._stamp_buttons.append(btn)

    def _select_stamp(self, name):
        """Select a stamp from the library."""
        self.stamp_selected = name
        self._update_stamp_buttons()
```

**Step 6: Add stamp placement in `on_canvas_press()`**

In `on_canvas_press()`, after the step tool handler (line ~2858) and before the general drawing setup at the end, add:
```python
        # Handle stamp tool — place stamp on click
        elif self.current_tool == 'stamp':
            self.drawing = False
            self.save_state()
            self._place_stamp(ix, iy)
            return
```

Wait — the structure of `on_canvas_press` sets `self.drawing = True` and `self.start_x/y` before checking tools. The stamp should intercept early. Place it in the tool-specific section near text/step.

**Step 7: Add `_place_stamp()` method**

```python
    def _place_stamp(self, ix, iy):
        """Place the selected stamp at image coordinates (ix, iy) using 4x supersampling."""
        SS = 4
        size = self.stamp_size
        big_size = size * SS

        # Create supersampled tile with transparency
        tile = Image.new('RGBA', (big_size, big_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(tile)

        # Draw shadow
        shadow_off = max(1, SS)
        shadow_tile = Image.new('RGBA', (big_size, big_size), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_tile)
        self._draw_stamp(shadow_draw, self.stamp_selected,
                         big_size // 2 + shadow_off, big_size // 2 + shadow_off * 2,
                         big_size - shadow_off * 4, '#000000')
        from PIL import ImageFilter
        shadow_tile = shadow_tile.filter(ImageFilter.GaussianBlur(radius=SS * 2))
        # Reduce shadow opacity
        shadow_data = shadow_tile.split()
        shadow_tile.putalpha(shadow_data[3].point(lambda a: a * 140 // 255))

        # Draw stamp on tile
        self._draw_stamp(draw, self.stamp_selected,
                         big_size // 2, big_size // 2,
                         big_size - shadow_off * 4, self.current_color)

        # Composite shadow under stamp
        final = Image.alpha_composite(shadow_tile, tile)

        # Downsample
        final = final.resize((size, size), Image.LANCZOS)

        # Paste onto image
        paste_x = int(ix - size // 2)
        paste_y = int(iy - size // 2)

        if self.image.mode != 'RGBA':
            self.image = self.image.convert('RGBA')
        # Expand canvas if needed (stamps near edges)
        base = self.image.copy()
        base.paste(final, (paste_x, paste_y), final)
        self.image = base.convert('RGB')

        self.refresh_display()
```

**Step 8: Update `set_tool()` for stamp props panel**

Add `self.stamp_props_frame.pack_forget()` to all existing branches. Add new branch:
```python
        elif tool == 'stamp':
            self.stamp_props_frame.pack(side='top', fill='x')
            # hide others...
```

**Step 9: Verify syntax and commit**
```bash
python -c "import py_compile; py_compile.compile('screensnap.py', doraise=True)"
git add screensnap.py
git commit -m "feat: add stamp library annotation tool with 14 vector icons"
```

---

### Task 4: Speech Bubbles / Modern Callout Tool (Shortcut: B)

Deferred rendering — stays as canvas items while editable, burned into `self.image` on save.

**Files:**
- Modify: `screensnap.py`

**Step 1: Enable bubble in overflow menu**

Add `'bubble'` to `self._implemented_overflow`.

**Step 2: Add bubble state variables to `__init__()`**

```python
        # Bubble tool properties
        self.bubble_elements = []
        self.selected_bubble_id = None
        self.dragging_bubble = False
        self.drag_bubble_offset_x = 0
        self.drag_bubble_offset_y = 0
        self.bubble_counter = 0
```

**Step 3: Add bubble properties panel**

Simple panel with font size spinner (reuses text tool's font size range):
```python
        # Bubble properties panel
        self.bubble_props_frame = tk.Frame(self.props_container, bg=Theme.SURFACE, padx=15, pady=10)
        self.bubble_props_frame.pack(side='top', fill='x')
        self.bubble_props_frame.pack_forget()

        tk.Label(self.bubble_props_frame, text="BUBBLE TOOL", font=("Segoe UI Bold", 8),
                 fg=Theme.PRIMARY, bg=Theme.SURFACE).pack(side='left', padx=(0, 20))

        tk.Label(self.bubble_props_frame, text="Font Size", font=Theme.FONT_LABEL,
                 fg=Theme.ON_SURFACE_VARIANT, bg=Theme.SURFACE).pack(side='left', padx=(0, 5))
        self.bubble_font_size_var = tk.IntVar(value=14)
        ttk.Spinbox(self.bubble_props_frame, from_=8, to=48,
                    textvariable=self.bubble_font_size_var, width=5).pack(side='left', padx=(0, 20))

        ModernButton(self.bubble_props_frame, text="🗑 DELETE", variant="danger",
                     command=self.delete_selected_bubble, font=("Segoe UI Bold", 8)).pack(side='left', padx=5)
```

**Step 4: Add bubble placement in `on_canvas_press()`**

When bubble tool is active and user clicks, create a new bubble:
```python
        elif self.current_tool == 'bubble':
            # Check if clicking on existing bubble to drag
            clicked_bubble = self._find_bubble_at(ix, iy)
            if clicked_bubble:
                self.selected_bubble_id = clicked_bubble['id']
                self.dragging_bubble = True
                self._drag_snapshot_taken = False
                self.drag_bubble_offset_x = ix - clicked_bubble['x']
                self.drag_bubble_offset_y = iy - clicked_bubble['y']
            else:
                self.drawing = False
                self._add_bubble(ix, iy)
            return
```

**Step 5: Add `_add_bubble()` method**

```python
    def _add_bubble(self, anchor_x, anchor_y):
        """Create a new speech bubble at the given anchor point."""
        self.save_state()
        self.bubble_counter += 1

        # Offset bubble body from anchor
        bx = anchor_x + 60
        by = anchor_y - 50
        font_size = self.bubble_font_size_var.get()

        elem = {
            'id': self.bubble_counter,
            'x': bx, 'y': by,            # bubble body position
            'anchor_x': anchor_x, 'anchor_y': anchor_y,
            'text': 'Type here...',
            'color': self.current_color,
            'font_size': font_size,
            'canvas_ids': {},
        }
        self.bubble_elements.append(elem)
        self._render_bubble_canvas(elem)

        # Enter edit mode immediately
        self._edit_bubble_text(elem)
```

**Step 6: Add `_render_bubble_canvas()` method**

Creates canvas items: connector line, rounded rectangle background, text, anchor dot.
```python
    def _render_bubble_canvas(self, elem):
        """Create/update canvas items for a bubble element."""
        z = self.zoom if self.zoom else 1.0

        # Remove old canvas items
        for key, cid in elem.get('canvas_ids', {}).items():
            try:
                self.canvas.delete(cid)
            except Exception:
                pass
        elem['canvas_ids'] = {}

        bx, by = elem['x'] * z, elem['y'] * z
        ax, ay = elem['anchor_x'] * z, elem['anchor_y'] * z

        # Estimate text size for bubble dimensions
        font_size = max(1, int(round(elem['font_size'] * z)))
        text_lines = elem['text'].split('\n')
        char_w = font_size * 0.6
        text_w = max(len(line) for line in text_lines) * char_w + 20
        text_h = len(text_lines) * (font_size + 4) + 16
        text_w = max(text_w, 80)

        # Connector line
        elem['canvas_ids']['line'] = self.canvas.create_line(
            ax, ay, bx + text_w / 2, by + text_h / 2,
            fill=elem['color'], width=max(1, int(1.5 * z)),
        )

        # Anchor dot
        dot_r = max(3, int(4 * z))
        elem['canvas_ids']['anchor'] = self.canvas.create_oval(
            ax - dot_r, ay - dot_r, ax + dot_r, ay + dot_r,
            fill=elem['color'], outline='',
        )

        # Rounded rectangle background (approximated with rectangle + ovals at corners)
        cr = max(4, int(8 * z))  # corner radius
        # Use a simple rectangle for now (true rounded rect requires polygon math)
        elem['canvas_ids']['bg'] = self.canvas.create_rectangle(
            bx, by, bx + text_w, by + text_h,
            fill=elem['color'], outline=Theme.OUTLINE, width=1,
            stipple='gray75',  # semi-transparent effect
        )

        # Text
        elem['canvas_ids']['text'] = self.canvas.create_text(
            bx + 10, by + 8,
            text=elem['text'],
            fill='white',
            font=('Segoe UI', font_size),
            anchor='nw',
            width=text_w - 20,
        )
```

**Step 7: Add `_edit_bubble_text()`, `_find_bubble_at()`, `delete_selected_bubble()` methods**

```python
    def _edit_bubble_text(self, elem):
        """Open inline text editing for a bubble."""
        new_text = self.prompt_text(elem['text'])
        if new_text and new_text != elem['text']:
            elem['text'] = new_text
            self._render_bubble_canvas(elem)

    def _find_bubble_at(self, ix, iy):
        """Find bubble element at image-space position."""
        for elem in reversed(self.bubble_elements):
            # Check if near bubble body
            font_size = elem['font_size']
            text_lines = elem['text'].split('\n')
            char_w = font_size * 0.6
            w = max(len(line) for line in text_lines) * char_w + 20
            h = len(text_lines) * (font_size + 4) + 16
            w = max(w, 80)
            if elem['x'] <= ix <= elem['x'] + w and elem['y'] <= iy <= elem['y'] + h:
                return elem
        return None

    def delete_selected_bubble(self):
        """Delete the currently selected bubble."""
        if self.selected_bubble_id is None:
            return
        self.save_state()
        for elem in self.bubble_elements:
            if elem['id'] == self.selected_bubble_id:
                for cid in elem.get('canvas_ids', {}).values():
                    try:
                        self.canvas.delete(cid)
                    except Exception:
                        pass
                self.bubble_elements.remove(elem)
                break
        self.selected_bubble_id = None
```

**Step 8: Add bubble dragging in `on_canvas_drag()`**

At the top of `on_canvas_drag()`, after step dragging handler:
```python
        # Handle bubble dragging
        if self.dragging_bubble and self.selected_bubble_id is not None:
            if not getattr(self, '_drag_snapshot_taken', False):
                self.save_state()
                self._drag_snapshot_taken = True
            cx, cy = self.get_canvas_coords(event)
            z = self.zoom if self.zoom else 1.0
            ix, iy = cx / z, cy / z
            for elem in self.bubble_elements:
                if elem['id'] == self.selected_bubble_id:
                    elem['x'] = ix - self.drag_bubble_offset_x
                    elem['y'] = iy - self.drag_bubble_offset_y
                    self._render_bubble_canvas(elem)
                    break
            return
```

**Step 9: Handle bubble release in `on_canvas_release()`**

At the top, after step release:
```python
        if self.dragging_bubble:
            self.dragging_bubble = False
            return
```

**Step 10: Add double-click to re-edit**

In `on_canvas_double_click()`:
```python
        # Check for bubble double-click
        if self.current_tool == 'bubble':
            clicked_bubble = self._find_bubble_at(x, y)
            if clicked_bubble:
                new_text = self.prompt_text(clicked_bubble['text'])
                if new_text and new_text != clicked_bubble['text']:
                    self.save_state()
                    clicked_bubble['text'] = new_text
                    self._render_bubble_canvas(clicked_bubble)
                return
```

**Step 11: Add bubble rendering on save**

In `render_annotations_to_image()`, after text rendering:
```python
        # Render bubble elements
        for elem in self.bubble_elements:
            try:
                from PIL import ImageFont
                font = ImageFont.truetype("arial.ttf", elem['font_size'])
            except:
                font = ImageFont.load_default()

            # Connector line
            draw.line([(elem['anchor_x'], elem['anchor_y']), (elem['x'] + 40, elem['y'] + 20)],
                      fill=elem['color'], width=2)

            # Anchor dot
            dot_r = 4
            draw.ellipse([elem['anchor_x'] - dot_r, elem['anchor_y'] - dot_r,
                          elem['anchor_x'] + dot_r, elem['anchor_y'] + dot_r],
                         fill=elem['color'])

            # Background rectangle
            text_bbox = draw.textbbox((elem['x'], elem['y']), elem['text'], font=font)
            pad = 10
            bg_rect = [text_bbox[0] - pad, text_bbox[1] - pad,
                       text_bbox[2] + pad, text_bbox[3] + pad]

            # Semi-transparent background via overlay
            bg_img = Image.new('RGBA', self.image.size, (0, 0, 0, 0))
            bg_draw = ImageDraw.Draw(bg_img)
            # Parse color to RGB tuple for alpha overlay
            r, g, b = self.image.convert('RGB').getpixel((0, 0))  # fallback
            try:
                r = int(elem['color'][1:3], 16)
                g = int(elem['color'][3:5], 16)
                b = int(elem['color'][5:7], 16)
            except:
                pass
            bg_draw.rectangle(bg_rect, fill=(r, g, b, 204))  # ~80% opacity
            bg_draw.text((elem['x'], elem['y']), elem['text'], fill='white', font=font)

            if self.image.mode != 'RGBA':
                self.image = self.image.convert('RGBA')
            self.image = Image.alpha_composite(self.image, bg_img)
            self.image = self.image.convert('RGB')
```

**Step 12: Update `_snapshot_state()` and `_apply_state()` for bubbles**

In `_snapshot_state()`:
```python
        return {
            'image': self.image.copy(),
            'text_elements': self._snapshot_text_elements(),
            'step_elements': self._snapshot_step_elements(),
            'step_counter': self.step_counter,
            'bubble_elements': [dict(e, canvas_ids={}) for e in self.bubble_elements],
            'bubble_counter': self.bubble_counter,
        }
```

In `_apply_state()`:
```python
        # Restore bubbles
        for elem in self.bubble_elements:
            for cid in elem.get('canvas_ids', {}).values():
                try:
                    self.canvas.delete(cid)
                except Exception:
                    pass
        self.bubble_elements = [dict(e) for e in state.get('bubble_elements', [])]
        self.bubble_counter = state.get('bubble_counter', 0)
        self.selected_bubble_id = None
        # Re-render bubble canvas items
        for elem in self.bubble_elements:
            elem['canvas_ids'] = {}
            self._render_bubble_canvas(elem)
```

**Step 13: Update `set_tool()` for bubble props panel**

Add `self.bubble_props_frame.pack_forget()` to all branches. Add new branch:
```python
        elif tool == 'bubble':
            self.bubble_props_frame.pack(side='top', fill='x')
            # hide others...
```

**Step 14: Verify syntax and commit**
```bash
python -c "import py_compile; py_compile.compile('screensnap.py', doraise=True)"
git add screensnap.py
git commit -m "feat: add speech bubble annotation tool with deferred rendering"
```

---

### Task 5: Smart Move Tool (Shortcut: V)

Two-phase interaction: select region, then drag to reposition. Fills vacated area with clone-stamp border sampling.

**Files:**
- Modify: `screensnap.py`

**Step 1: Enable smart_move in overflow menu**

Add `'smart_move'` to `self._implemented_overflow`.

**Step 2: Add smart_move state variables**

```python
        # Smart move tool state
        self.smart_move_phase = 'select'  # 'select' or 'move'
        self.smart_move_region = None     # (x1, y1, x2, y2) in image coords
        self.smart_move_snapshot = None   # Image copy of selected region
        self.smart_move_preview_ids = []  # Canvas item IDs for selection preview
```

**Step 3: Handle smart_move in `on_canvas_press()`**

```python
        elif self.current_tool == 'smart_move':
            if self.smart_move_phase == 'move' and self.smart_move_region:
                # Start moving the selected region
                self.dragging_smart_move = True
                self._drag_snapshot_taken = False
                self.smart_move_drag_start_x = ix
                self.smart_move_drag_start_y = iy
            # else: selection phase — normal drawing behavior handles it
```

**Step 4: Handle smart_move drag preview**

In `on_canvas_drag()`, add smart move drag handling and selection preview:
```python
        # Handle smart move dragging
        if getattr(self, 'dragging_smart_move', False):
            cx, cy = self.get_canvas_coords(event)
            z = self.zoom if self.zoom else 1.0
            ix, iy = cx / z, cy / z
            # Move preview
            dx = ix - self.smart_move_drag_start_x
            dy = iy - self.smart_move_drag_start_y
            for cid in self.smart_move_preview_ids:
                try:
                    self.canvas.delete(cid)
                except:
                    pass
            self.smart_move_preview_ids.clear()
            r = self.smart_move_region
            nx1, ny1 = (r[0] + dx) * z, (r[1] + dy) * z
            nx2, ny2 = (r[2] + dx) * z, (r[3] + dy) * z
            self.smart_move_preview_ids.append(
                self.canvas.create_rectangle(nx1, ny1, nx2, ny2,
                                             outline='#00FF00', width=2, dash=(5, 5))
            )
            return
```

And in the normal preview section:
```python
        # Draw preview for smart_move selection
        if self.current_tool == 'smart_move' and self.smart_move_phase == 'select':
            self.current_shape = self.canvas.create_rectangle(
                self.start_x, self.start_y, x, y,
                outline='#00FF00',
                width=2,
                dash=(5, 5),
            )
            return
```

**Step 5: Handle smart_move release**

In `on_canvas_release()`, before the existing bounds calc:
```python
        if self.current_tool == 'smart_move':
            if self.smart_move_phase == 'select':
                # Region selected — capture it and enter move phase
                z = self.zoom if self.zoom else 1.0
                ix1, iy1 = min(self.start_x, x) / z, min(self.start_y, y) / z
                ix2, iy2 = max(self.start_x, x) / z, max(self.start_y, y) / z
                if ix2 - ix1 < 5 or iy2 - iy1 < 5:
                    return
                self.smart_move_region = (ix1, iy1, ix2, iy2)
                self.smart_move_snapshot = self.image.crop(
                    (int(ix1), int(iy1), int(ix2), int(iy2))
                ).copy()
                self.smart_move_phase = 'move'
                # Show dashed selection on canvas
                self.smart_move_preview_ids.append(
                    self.canvas.create_rectangle(
                        ix1 * z, iy1 * z, ix2 * z, iy2 * z,
                        outline='#00FF00', width=2, dash=(5, 5)
                    )
                )
                self.status_var.set("SMART MOVE: Drag selection to new position")
                return
            elif getattr(self, 'dragging_smart_move', False):
                # Drop at new position
                self.dragging_smart_move = False
                cx, cy = self.get_canvas_coords(event)
                z = self.zoom if self.zoom else 1.0
                ix, iy = cx / z, cy / z
                dx = ix - self.smart_move_drag_start_x
                dy = iy - self.smart_move_drag_start_y

                self.save_state()
                r = self.smart_move_region
                # Fill vacated area
                self._fill_vacated_region(int(r[0]), int(r[1]), int(r[2]), int(r[3]))
                # Paste at new position
                new_x = int(r[0] + dx)
                new_y = int(r[1] + dy)
                self.image.paste(self.smart_move_snapshot, (new_x, new_y))

                # Clean up
                for cid in self.smart_move_preview_ids:
                    try:
                        self.canvas.delete(cid)
                    except:
                        pass
                self.smart_move_preview_ids.clear()
                self.smart_move_phase = 'select'
                self.smart_move_region = None
                self.smart_move_snapshot = None
                self.refresh_display()
                return
```

**Step 6: Add `_fill_vacated_region()` method**

```python
    def _fill_vacated_region(self, x1, y1, x2, y2):
        """Fill a vacated rectangle by sampling border pixels and blending inward."""
        img = self.image
        w, h = img.size
        border = min(16, (x2 - x1) // 2, (y2 - y1) // 2)
        if border < 1:
            border = 1

        # Sample border strips (clamped to image bounds)
        for y in range(y1, y2):
            for x in range(x1, x2):
                # Distance from each edge
                dl = x - x1  # from left
                dr = x2 - 1 - x  # from right
                dt = y - y1  # from top
                db = y2 - 1 - y  # from bottom

                # Sample from outside the region at nearest edge
                samples = []
                weights = []

                if dl < border and x1 > 0:
                    src_x = max(0, x1 - 1)
                    w_val = 1.0 - (dl / border)
                    samples.append(img.getpixel((src_x, min(y, h - 1))))
                    weights.append(w_val)

                if dr < border and x2 < w:
                    src_x = min(w - 1, x2)
                    w_val = 1.0 - (dr / border)
                    samples.append(img.getpixel((src_x, min(y, h - 1))))
                    weights.append(w_val)

                if dt < border and y1 > 0:
                    src_y = max(0, y1 - 1)
                    w_val = 1.0 - (dt / border)
                    samples.append(img.getpixel((min(x, w - 1), src_y)))
                    weights.append(w_val)

                if db < border and y2 < h:
                    src_y = min(h - 1, y2)
                    w_val = 1.0 - (db / border)
                    samples.append(img.getpixel((min(x, w - 1), src_y)))
                    weights.append(w_val)

                if samples and weights:
                    total_w = sum(weights)
                    r = sum(s[0] * w for s, w in zip(samples, weights)) / total_w
                    g = sum(s[1] * w for s, w in zip(samples, weights)) / total_w
                    b = sum(s[2] * w for s, w in zip(samples, weights)) / total_w
                    img.putpixel((x, y), (int(r), int(g), int(b)))
```

**Step 7: Reset smart_move state when switching tools**

In `set_tool()`, in the else branch (or at the top of the method):
```python
        # Reset smart_move state when switching away
        if self.current_tool == 'smart_move' and tool != 'smart_move':
            self.smart_move_phase = 'select'
            self.smart_move_region = None
            self.smart_move_snapshot = None
            for cid in self.smart_move_preview_ids:
                try:
                    self.canvas.delete(cid)
                except:
                    pass
            self.smart_move_preview_ids.clear()
```

**Step 8: Update `set_tool()` for props (no panel needed, just hide others)**

Smart Move has no properties panel per spec. Just add `pack_forget` calls.

**Step 9: Verify syntax and commit**
```bash
python -c "import py_compile; py_compile.compile('screensnap.py', doraise=True)"
git add screensnap.py
git commit -m "feat: add smart move tool with clone-stamp region fill"
```

---

## Execution Order

1. **Highlight** (Task 1) — simplest, ~20 lines
2. **Blur/Pixelate** (Task 2) — simple with props panel, ~60 lines
3. **Stamp Library** (Task 3) — moderate complexity, ~200 lines
4. **Speech Bubbles** (Task 4) — complex, deferred rendering, ~250 lines
5. **Smart Move** (Task 5) — complex, two-phase interaction, ~150 lines
