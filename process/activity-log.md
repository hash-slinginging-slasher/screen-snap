## 2026-04-12

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
