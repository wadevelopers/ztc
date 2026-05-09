# Plan: editable `default_bg` per-pane in the layout editor

## Context

Zellij supports a per-pane background color via the `default_bg "#hex"`
directive (typically a child node of `pane`, also accepted as a
property `default_bg="#hex"`). The user already uses it manually in
`~/.config/zellij/layouts/dev.kdl` (lines 13, 20, 24, 32).

ZTC currently preserves the value on roundtrip via the `Pane`
model's `raw_unknown_nodes` field, so files with `default_bg` are
never corrupted. But the value is invisible to the editor — the user
cannot view, change or unset it from the TUI.

This plan promotes `default_bg` to a first-class `Pane` field and
makes it editable.

## Pre-existing bug (fix BEFORE Stage 1)

`src/ztc/sessions/services/session_info.py:242` reads `default_bg`
only as a property:

```python
bg = child.props.get("default_bg")
```

But hand-written Zellij layouts (like the user's `dev.kdl`) put it as
a child node, e.g.:

```kdl
pane command="btop" {
    default_bg "#14171f"
}
```

Result: when the sessions detail tries to render its colored swatches,
panes from hand-written layouts always fall back to the neutral gray
because their `default_bg` is invisible to the parser. Only sessions
restored from a layout that Zellij itself dumped (where Zellij uses
the property form) show the color.

**Fix**: in `_collect_layout_panes`, after checking the property,
also look at child nodes for a `default_bg` node with a string arg.
~5 lines change. **Bundled with the v1.0.0 launcher-refactor commit**
— see `PLAN_LAUNCHER_REFACTOR.md` for that commit's full scope and
acceptance criteria. Stage 1 of *this* plan starts after that commit
is tagged as v1.0.0.

## Stage 1 — make `default_bg` editable (text + hex validation)

### Files

| # | Path | Change |
|---|---|---|
| 1 | `src/ztc/models/layout.py` | Add `default_bg: str \| None = None` to `Pane` |
| 2 | `src/ztc/zellij/layout_io.py` | Parser: accept both child-node and property forms. Writer: emit as child node. Add to `_PANE_CHILD_FIELDS`. |
| 3 | `src/ztc/zellij/layout_ops.py` | `split_pane`: propagate `default_bg` to `inner_existing` so the color is not lost when a colored pane is split |
| 4 | `src/ztc/widgets/confirm.py` | `PaneEditModal`: add a "Default bg" row (Input with placeholder `#rrggbb`). On submit: validate via `is_valid_hex` from `services/colors.py`. On invalid: show notification, do not dismiss. Empty = `None`. Applies to both leaves and containers. |
| 5 | `tests/zellij/test_layout_io.py` | (a) Roundtrip with `default_bg` (both forms parse to model; emit-back uses child-node form consistently). (b) `split_pane` preserves `default_bg` on `inner_existing`. (c) `PaneEditModal` happy-path + invalid-hex rejection. |

### Design decisions

- **Emission form: child node** `default_bg "#color"`, not property.
  Rationale: it is the idiomatic Zellij syntax (used in the user's
  existing files and in Zellij examples), and it preserves roundtrip
  fidelity for hand-written layouts. The cost is a slightly longer
  block when the only attribute on the pane is `default_bg` (since
  the writer needs to open `{...}` for it), but readability wins.

- **Parsing form: accept both** child node and property. Property
  form appears in layouts that Zellij itself dumps (via the sessions
  feature), and there is no reason to reject those.

- **Validation: strict on submit**. Empty input = unset. Non-empty
  must match `is_valid_hex` (`#rgb`, `#rrggbb`, `#rrggbbaa`, etc.,
  whatever the existing helper accepts). On invalid, show a Textual
  notification and keep the modal open. No live validation while
  typing — kept simple.

- **Applicability: leaf and container panes**. Zellij accepts
  `default_bg` on both — the user's `dev.kdl:20` is a container pane
  with `default_bg`.

### Out of scope for Stage 1

- Tab-level `default_bg` (Zellij does not support it).
- Visual color picker / swatches in the modal or pane tree (deferred
  to Stage 2).
- Other pane-level theme overrides — none currently exist in Zellij;
  only `default_bg`.

## Stage 2 — visual UX (follow-up plan)

Goal: bring the layout editor to visual parity with the sessions
detail view, where each pane shows a swatch of its `default_bg`.

### Files

| # | Path | Change |
|---|---|---|
| 1 | `src/ztc/services/colors.py` | Extract `bg_swatch()` and `contrast_text_color()` from `sessions/screens/picker.py:390-409`. They are general color utilities, not session-specific. |
| 2 | `src/ztc/sessions/screens/picker.py` | Replace the private `_bg_swatch` and `_contrast_text_color` methods with calls to the extracted helpers. Behavior unchanged. |
| 3 | `src/ztc/screens/layout_editor.py` | When rendering a pane in the tree label, prepend the swatch when `default_bg` is set. Mirrors the sessions detail. |
| 4 | `src/ztc/widgets/confirm.py` | Replace the plain Input in `PaneEditModal` with a color picker row: Input + live swatch preview next to it (same pattern as `EditColorModal`'s preview, inlined into the form). Optional: a small palette of the active Zellij theme's colors as quick-pick buttons. |
| 5 | tests | Visual rendering helpers; modal swatch updates as the user types |

### Open questions for Stage 2

- Should the modal also offer a quick-pick palette of the active
  theme's colors (`bg`, `black`, `blue`, etc.)? Useful but adds
  layout complexity. Decide when entering Stage 2.

## Notes for review

- **Highest uncertainty in Stage 1**: whether to enforce hex
  validation (strict, modal stays open) or accept anything (lenient,
  Zellij silently ignores invalid). Decided **strict** per user
  request.
- **File counts**: Stage 1 = 5 files; Stage 2 = 5 files (one is a
  pure refactor, one is the picker.py adjustment).
- **Commit boundaries**:
  1. The pre-existing `default_bg` parsing bug ships as part of the
     v1.0.0 launcher-refactor commit — see `PLAN_LAUNCHER_REFACTOR.md`.
     Stage 1 of *this* plan starts only after that commit is tagged
     as `v1.0.0`.
  2. Stage 1 (own commit, target version: v1.1.0).
  3. Stage 2 (own commit, also v1.1.0 or split into v1.1.x / v1.2.0
     depending on what other roadmap items it ships with).
