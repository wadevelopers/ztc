# Plan: Kitty theme + settings import (parity with Alacritty)

Target version: **v1.2.0**, Stage A (prerequisite to
`PLAN_FILE_PICKER.md` / Stage B).

## Context

`ColorEditorScreen.action_import` and
`TerminalSettingsScreen.action_import` are the two import flows the
app exposes today. Both currently exit early with a "not supported"
toast when the active backend is Kitty:

```python
if not isinstance(self.backend, AlacrittyBackend):
    self.app.notify(f"... not supported on {self.backend.display_name}.", ...)
    return
```

Only Alacritty has the import capability wired. This is historical,
not a technical limitation — Kitty's parser, slot reader/writer and
settings reader/writer all already exist; what is missing is the
`import_theme_file` method on `KittyBackend` and the removal of the
two `isinstance` guards.

The file picker plan (Stage B of v1.2.0) modernizes both import flows
to use a `FilePickerModal` instead of the current `PromptModal`. To
avoid leaving the file picker as Alacritty-only with an awkward
"if Kitty, do nothing" branch, we add Kitty parity first (Stage A).

## Scope

Strict feature parity with Alacritty's existing import:

- **Theme import** in the color editor: copy color slots from a
  source Kitty `.conf` file into the current Kitty config.
- **Settings import** in the terminal settings screen: copy
  `padding x/y`, `opacity`, `font.family`, `font.size`,
  `cursor.shape` from a source `.conf` into the current config.
  This flow is already protocol-based (uses `load`,
  `read_setting`, `write_setting`) and works for any backend
  that implements the protocol — only the `isinstance` guard
  blocks Kitty today.

Out of scope: cross-backend import (importing from `.toml` into a
Kitty config or vice versa). The format mismatch is non-trivial; if
that capability is wanted later, it's its own design problem.

## Files

| # | Path | Change |
|---|---|---|
| 1 | `src/ztc/services/terminals/__init__.py` | Add `import_theme_file(doc: BackendDoc, source_path: Path) -> int` to the `TerminalBackend` Protocol. Doc: "copies color slots from another config of the same backend; returns count of slots overwritten; raises `FileNotFoundError` if `source_path` does not exist". This lets the color editor call `self.backend.import_theme_file(...)` without an `isinstance` narrowing. |
| 2 | `src/ztc/services/terminals/kitty.py` | Add `KittyBackend.import_theme_file(doc, source_path) -> int`. Body mirrors `AlacrittyBackend.import_theme_file` literally: raise `FileNotFoundError` if `source_path` does not exist; open via `self.load`; iterate `KNOWN_SLOTS` (Kitty's own list at line 84); for each slot read the source value with `self.read_slot`; **skip if `value is None or not is_valid_hex(value)`** (matches Alacritty's filter — `normalize_hex` would error on invalid input); on valid, write via `self.write_slot(doc, slot, normalize_hex(value))`; count overwrites; return. |
| 3 | `src/ztc/services/terminals/alacritty.py` | No logic change. Existing `import_theme_file` already matches the new protocol signature; just verify during implementation. |
| 4 | `src/ztc/screens/color_editor.py` | Remove the `if not isinstance(self.backend, AlacrittyBackend)` guard in `action_import` (~line 257). The remaining body works as-is because it uses protocol methods. Update the comment "Capability solo de Alacritty: import desde otro alacritty.toml" to reflect the new reality. |
| 5 | `src/ztc/screens/terminal_settings.py` | Remove the equivalent guard in `action_import` (~line 270-275). The body is already protocol-based; no further change. Update the comment "Capability solo de Alacritty: import de settings desde otro alacritty.toml" likewise. |
| 6 | `tests/test_terminal_kitty.py` | Add unit tests for `KittyBackend.import_theme_file`: imports from a fixture `.conf`, asserts color slots are copied; missing source raises `FileNotFoundError`; invalid hex values are skipped. |
| 7 | `tests/test_color_editor_screen.py` (currently empty) | Add an integration test: open color editor with a Kitty backend, **first** monkey-patch `app.push_screen` to capture the second arg (the `after` callback), **then** call `screen.action_import()`. The callback is captured during that call; afterwards invoke it directly with a fixture `.conf` path. Assert no "not supported" toast (i.e. the action does not exit early before `push_screen`), and that `screen.dirty` is `True` and the doc has the imported slots. The modal itself is not exercised — that's Stage B's responsibility. |
| 8 | `tests/test_terminal_settings_screen.py` | Add an equivalent integration test for the settings import path with Kitty backend, using the same monkey-patch-before-action-import pattern. |

## Design decisions

- **Promote `import_theme_file` to the Protocol**, instead of leaving
  it as an Alacritty-only capability accessed via `isinstance`
  narrowing. Reason: the operation is conceptually backend-agnostic
  (read color slots from another config of the same backend, copy
  into the current), and Kitty's implementation is structurally
  identical. Promoting to the protocol makes the call site simpler
  and is the natural shape for any future third backend
  (Ghostty/WezTerm/etc.).

- **Same-backend import only** (no cross-backend). A Kitty source
  imports into Kitty; an Alacritty source imports into Alacritty.
  Cross-backend would require translating between `.toml` and
  `.conf` formats and resolving format mismatches, which is a
  separate design problem outside this plan's scope.

- **Mirror error handling**: `FileNotFoundError` if the source
  doesn't exist; load errors propagate from `self.load`. The
  caller (the screens) already handle these and show toast
  notifications.

- **Preserve `KNOWN_SLOTS` per-backend**. Each backend defines
  its own `KNOWN_SLOTS: list[CanonicalSlot]` reflecting which slots
  it supports. Kitty's at line 84 of `kitty.py`; Alacritty's at
  line 38 of `alacritty.py`. The new `KittyBackend.import_theme_file`
  uses Kitty's list. No consolidation in this plan.

## Out of scope

- Cross-backend import (Alacritty source into Kitty, etc.).
- File picker integration — that's Stage B (`PLAN_FILE_PICKER.md`).
  Stage A keeps the existing `PromptModal` for both backends; Stage B
  replaces it for both at once.
- Adding new categories of import (e.g., importing layouts or themes
  by name) that don't exist for Alacritty either.
- Refactoring the existing Alacritty implementation. Changes there
  are limited to verifying the protocol signature.

## Acceptance criteria

- `uv run pytest -q` passes including the new tests.
- `uv run ruff check` clean.
- `rg -n "isinstance\(.*AlacrittyBackend\)" src/ztc/screens/` returns
  zero matches in `color_editor.py` and `terminal_settings.py`
  (`action_import` paths) — the two guards are gone.
- Manual smoke test: with Kitty as the active backend, open the
  color editor, press `i` for import, type a path to a `.conf` file
  with color directives, confirm — colors land in the active
  config; save persists them. No "not supported" toast.
- Manual smoke test: same with terminal settings (e.g., padding,
  font from a source `.conf`).
- Alacritty paths continue working (no regression).

## Versioning

- This plan is **Stage A** of v1.2.0.
- Stage B (`PLAN_FILE_PICKER.md`) ships in the same v1.2.0.
- Per project rules, no version bump or tag is created at the end
  of Stage A. The bump to `1.2.0` and the `v1.2.0` tag happen after
  Stage B is committed and verified. Stage A produces one commit
  with the work; that's it.
