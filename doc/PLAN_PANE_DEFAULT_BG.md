# Plan: editable `default_bg` / `default_fg` per-pane in the layout editor

## Context

Zellij supports two per-pane visual overrides: `default_bg` (background
color of the pane area) and `default_fg` (foreground/text color).
Both can be expressed either as a child node (canonical Zellij style):

```kdl
pane {
    default_bg "#14171f"
    default_fg "#f8f8f2"
}
```

…or as a property:

```kdl
pane default_bg="#14171f" default_fg="#f8f8f2"
```

The user already uses `default_bg` manually in
`~/.config/zellij/layouts/dev.kdl`.

### Current state of preservation in ZTC

The picture is asymmetric depending on which KDL form the user
wrote:

- **Child-node form** (`pane { default_bg "#..." }`): preserved on
  roundtrip via the `Pane` model's `raw_unknown_nodes` field. The
  parser captures unknown child nodes there
  (`src/ztc/zellij/layout_io.py:128`) and the writer re-emits them
  verbatim (`src/ztc/zellij/layout_io.py:241-242`).
- **Property form** (`pane default_bg="#..."`): **lost on roundtrip**.
  There is no `raw_unknown_props` equivalent — unknown properties
  are silently dropped by the parser, and the writer has no record
  of them. A user who saved a layout from the editor would lose
  any property-form `default_bg`/`default_fg` that was in the
  original file.

In neither case can the user view, change or unset these values
through the TUI.

### Goals of this plan

This plan fixes both **visibility** (the editor can show and modify
the values) and **preservation** (both KDL forms survive roundtrip)
by promoting `default_bg` and `default_fg` to first-class `Pane`
fields. Once captured into the model, they are emitted in the
canonical child-node form regardless of which form the source file
used — this normalizes the file shape but never loses data.

Including `default_fg` in the same iteration is cheap (the
implementation is parallel to `default_bg`) and gives the user
complete visual control of a pane without having to touch terminal
colors.

## Pre-existing bug (already fixed in v1.0.0)

`src/ztc/sessions/services/session_info.py` only read `default_bg` as
a property. Hand-written layouts use the child-node form, so the
sessions detail view always rendered the neutral fallback for them.
Fixed in v1.0.0 (commit `469f96c`) via the `_read_default_bg` helper.
**Pending in this plan**: extend that helper to also read
`default_fg` once the model gains the field.

## Color format support

Verified empirically against Zellij using the `color-test` tab in
`~/.config/zellij/layouts/dev.kdl`. The four formats tested all
render with the declared color:

| Format | Example | Zellij accepts | Notes |
|---|---|---|---|
| `#rrggbb` | `#6272a4` | yes | most common |
| `#rgb` | `#6c8` | yes | 3-digit shorthand |
| `#rrggbbaa` | `#6272a480` | yes (syntactically) | **alpha is parsed but visually ignored** — renders identical to `#rrggbb` of the same RGB |
| `rgb:rr/gg/bb` | `rgb:6c/72/a4` | yes | X11 colon notation |

Both `default_bg` and `default_fg` accept all four formats.

### Validator

Goes in `src/ztc/services/colors.py` as a new helper
`is_valid_zellij_pane_color(value)` — separate from `is_valid_hex`
because the rule differs (`is_valid_hex` rejects `rgb:...`). The
function strips whitespace before matching, consistent with the
existing `is_valid_hex`:

```python
_ZELLIJ_PANE_COLOR = re.compile(
    r"^(?:"
    r"#[0-9a-fA-F]{3}"           # #rgb
    r"|#[0-9a-fA-F]{6}"          # #rrggbb
    r"|#[0-9a-fA-F]{8}"          # #rrggbbaa (alpha ignored visually)
    r"|rgb:[0-9a-fA-F]{2}/[0-9a-fA-F]{2}/[0-9a-fA-F]{2}"  # rgb:rr/gg/bb
    r")$"
)


def is_valid_zellij_pane_color(value: str) -> bool:
    return bool(_ZELLIJ_PANE_COLOR.match(value.strip()))
```

## Stage 1 — make `default_bg` and `default_fg` editable

### Files

| # | Path | Change |
|---|---|---|
| 1 | `src/ztc/models/layout.py` | Add `default_bg: str \| None = None` and `default_fg: str \| None = None` to `Pane` |
| 2 | `src/ztc/zellij/layout_io.py` | Parser: accept both child-node and property forms for both fields. Add to `_PANE_CHILD_FIELDS`. Writer: emit both as child nodes; **explicitly include `pane.default_bg is not None or pane.default_fg is not None` in `has_block`** so a pane that only has these fields still gets a `{...}` block (otherwise the writer would emit `pane` without block and silently drop the values). |
| 3 | `src/ztc/zellij/layout_ops.py` | `split_pane`: propagate `default_bg` and `default_fg` to `inner_existing` so the colors are not lost when a colored pane is split. |
| 4 | `src/ztc/services/colors.py` | New helper `is_valid_zellij_pane_color(value)` accepting the four pinned formats (see "Color format support" above). Strips whitespace before matching, mirroring `is_valid_hex`. |
| 5 | `src/ztc/widgets/confirm.py` | `PaneEditModal`: add "Default bg" and "Default fg" rows (Input with placeholder `#rrggbb` or `rgb:rr/gg/bb`). On submit: validate via `is_valid_zellij_pane_color`. On invalid: show notification, do not dismiss. Empty = `None`. Both fields shown for leaves and containers (Zellij accepts the directives on both, even if leaves are the common case). |
| 6 | `src/ztc/sessions/services/session_info.py` | Add `default_fg: str \| None = None` to `PaneInfo`. Extend the existing `_read_default_bg` helper into a generic `_read_color_attr(node, attr_name)` and call it for both `default_bg` and `default_fg`. |
| 7 | `tests/test_layout_io.py` | Roundtrip tests: parse a fixture KDL with both fields in both forms (child-node + property); assert model has them; emit-back; assert idempotent (canonical child-node form). |
| 8 | `tests/test_layout_ops.py` | `split_pane` preserves both `default_bg` and `default_fg` on `inner_existing`. |
| 9 | `tests/test_layout_editor_screen.py` | `PaneEditModal` happy-path (valid color saved) + invalid-color rejection (modal stays open). |
| 10 | `tests/sessions/test_session_info.py` | Add `test_default_fg_property_form` and `test_default_fg_child_node_form` mirroring the existing `default_bg` tests. |

### Design decisions

- **Emission form: child node** for both fields (`default_bg "#…"` and
  `default_fg "#…"`), not property. Rationale: idiomatic Zellij syntax,
  matches the user's existing `dev.kdl`, preserves roundtrip fidelity
  for hand-written layouts.

- **Parsing form: accept both** child node and property forms. Property
  form appears in layouts that Zellij itself dumps; the parser must
  not reject those.

- **Precedence when both forms appear in the same pane**: **property
  wins**. Mirrors the existing parser pattern in `_apply_child_field`
  (`src/ztc/zellij/layout_io.py`) where string fields like `command`,
  `cwd`, `size`, `name` are read first as properties, and the
  child-node fallback only applies when the field is still `None`.
  Hand-written layouts using both forms are rare-to-nonexistent, but
  documenting the rule avoids ambiguity if it ever comes up.

- **Validation: strict on submit** via `is_valid_zellij_pane_color`.
  Empty input = unset. Non-empty must match. On invalid, Textual
  notification and modal stays open. No live validation while typing.

- **Applicability: leaf and container panes**. Zellij accepts both
  directives on both — but in practice the user (and most layouts)
  use them only on leaves, since a container's bg is mostly hidden
  behind its children. The model and editor allow both; Stage 2's
  visual swatch is leaves-only (see below).

### Out of scope for Stage 1

- Tab-level `default_bg` / `default_fg`. Zellij does not support these
  at the tab level (only on panes).
- Visual color picker / swatches in the modal or pane tree (deferred
  to Stage 2).
- Other Zellij theme primitives (e.g. theme name overrides). Only
  `default_bg` and `default_fg` are pane-local visual overrides; the
  rest are theme-level.

## Stage 2 — visual UX (follow-up plan)

Goal: surface `default_bg` and `default_fg` visually in the layout
editor, consistent with how the sessions detail view already shows
swatches.

### Swatch placement policy

Sessions detail today (`src/ztc/sessions/screens/picker.py:343-358`)
shows swatches **only on leaves**, not on containers. Stage 2 mirrors
that policy in the layout editor:

- **Leaves with `default_bg` set**: show a swatch in the tree label
  and in the modal preview. If `default_fg` is also set, the swatch
  uses bg as background and fg as text color (preview shows actual
  rendered look). If `default_fg` is not set, the swatch uses an
  automatic contrast color (black or white based on bg luminance,
  same logic as the existing `_contrast_text_color`).
- **Leaves with only `default_fg` set (no bg)**: **no swatch**. A
  swatch needs a background to be meaningful, and rendering a
  one-cell foreground sample without context is more confusing than
  helpful. The fg value is still visible in the modal text input;
  it just has no visual preview in the tree.
- **Containers**: no swatch even if either field is set. Containers
  are structural; their visible area is mostly covered by children.

If at some point we observe that containers with these fields are
common in the wild, both views (sessions detail and layout editor)
should be updated together to add container swatches — but that is
a separate iteration, not Stage 2.

### Files

| # | Path | Change |
|---|---|---|
| 1 | `src/ztc/services/colors.py` | Extract `bg_swatch()` and `contrast_text_color()` from `sessions/screens/picker.py:390-409`. They are general color utilities, not session-specific. Extend `bg_swatch` to take an optional `fg` parameter so it can render with a custom foreground. |
| 2 | `src/ztc/sessions/screens/picker.py` | Replace the private `_bg_swatch` and `_contrast_text_color` methods with calls to the extracted helpers. Pass the new `default_fg` from the model when present. Behavior unchanged when only bg is set. |
| 3 | `src/ztc/screens/layout_editor.py` | When rendering a leaf pane in the tree label, prepend the swatch when `default_bg` is set (per the swatch placement policy above). Containers and leaves with only `default_fg` get no swatch. |
| 4 | `src/ztc/widgets/confirm.py` | Replace the plain Inputs in `PaneEditModal` with rows that show a live swatch preview next to the Input (same pattern as `EditColorModal`'s preview, inlined). The combined swatch shows bg+fg as the user types. |
| 5 | tests | Visual rendering helpers; modal swatch updates as the user types. |

### Open questions for Stage 2

- Should the modal also offer a quick-pick palette of the active
  Zellij theme's colors (`bg`, `black`, `blue`, etc.)? Useful but
  adds layout complexity. Decide when entering Stage 2.

## Notes for review

- **Color format support: pinned**. All four formats verified to
  render in Zellij (see "Color format support" above). Validator
  regex accepts the union: `#rgb`, `#rrggbb`, `#rrggbbaa` (alpha
  ignored visually but accepted syntactically), and `rgb:rr/gg/bb`.
- **File counts**: Stage 1 = 10 files; Stage 2 = 5 files (one is a
  pure refactor, one is the picker.py adjustment, three are new UI
  / tests).
- **Commit boundaries**:
  1. The pre-existing `default_bg` parsing bug already shipped in
     v1.0.0 (commit `469f96c`). The parallel `default_fg` parsing
     extension is part of Stage 1 of this plan, not a prep commit.
  2. Stage 1 (own commit, target version: v1.1.0).
  3. Stage 2 (own commit, also v1.1.0 or split into v1.1.x / v1.2.0
     depending on what other roadmap items it ships with).
