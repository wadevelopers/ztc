# Plan: reusable file picker (`FilePickerModal`)

Target version: **v1.3.0**. Originally scoped for v1.2.0, repackaged
when v1.2.0 expanded to cover the full Kitty parity story (import +
auto-reload). Stage A of v1.2.0 (Kitty import) is the only hard
prerequisite for this plan and is already shipped in commit
`f363beb`.

## Context

Two places in the app today require the user to type a filesystem
path into a text input:

- **`action_import`** in `src/ztc/screens/color_editor.py` (and the
  equivalent flow in `src/ztc/screens/terminal_settings.py` —
  confirmed to exist): currently a `PromptModal` asks for a filename
  (resolved against the backend's config dir) or an absolute path.
- **Pane "Command" field** in `PaneEditModal`
  (`src/ztc/widgets/confirm.py`): a plain `Input` where the user types
  a command name (resolved via `$PATH` like `bash`, `vim`) or an
  absolute/relative path to a script.

In both cases the friction is the same: the user has to remember the
exact filename and type it out. Especially when pointing at scripts
or themes saved months ago.

This plan introduces a reusable `FilePickerModal` that lets the user
**browse the filesystem** with Textual's built-in `DirectoryTree`
widget, while keeping a free-form `Input` so the user can still type
a command directly without browsing.

## Scope

A single iteration covering:

- A reusable `FilePickerModal` widget.
- Integration in the import flow (replaces the current `PromptModal`).
- Integration in the pane command flow (adds a "Find" entry-point to
  open the picker; field still accepts free text for `$PATH` commands).

No follow-up stages planned. If new use cases for path input appear
later, the same widget is reused — no further design needed.

## API of `FilePickerModal` (explicit, not ambiguous)

The modal accepts these parameters, **with `initial_dir` separate from
`initial_value`** so it is impossible to confuse "where the tree opens"
with "what is pre-filled in the Input":

| Parameter | Type | Meaning |
|---|---|---|
| `title` | `str` | Modal header (e.g. "Import theme from file") |
| `initial_dir` | `Path` | Where the `DirectoryTree` opens. Should normally exist; if not, the tree renders empty and the user can type a path manually in the Input |
| `initial_value` | `str` | Pre-fill of the Input. Default `""`. The Input is editable; the user can type any path |
| `allow_empty` | `bool` | If `False`, Confirm is disabled when the Input is empty. Default `False` |
| `extensions` | `list[str] \| None` | File-extension filter (e.g. `[".toml"]`). Directories are always shown regardless. Default `None` (no filter) |
| `show_hidden` | `bool` | Show dotfiles/dotdirs in the tree. Default `False` |

Both `extensions` and `show_hidden` are implemented via a subclass
`FilteredDirectoryTree(DirectoryTree)` that overrides
`filter_paths()`. Textual's stock `DirectoryTree` does **not** filter
hidden files (it just styles them differently) and has no built-in
extension filter — both must be implemented in the subclass.

## Files to touch

| # | Path | Change |
|---|---|---|
| 1 | `src/ztc/widgets/file_picker.py` (new) | `FilePickerModal[str \| None]` (the modal) + `FilteredDirectoryTree(DirectoryTree)` subclass with the `filter_paths()` override. Composes: `Input` (editable, pre-filled with `initial_value`) + `FilteredDirectoryTree` (rooted at `initial_dir`) + Cancel/Confirm. Tree-selecting a file updates the Input. Confirm is enabled per `allow_empty`; on Confirm the modal dismisses with `Input.value` (which may be empty if `allow_empty=True`). Cancel dismisses with `None`. |
| 2 | `src/ztc/screens/color_editor.py` (`action_import`) | Replace the `PromptModal` push with `FilePickerModal(title="Import theme from file", initial_dir=self.backend_path.parent, initial_value="", allow_empty=False, extensions=IMPORT_EXTENSIONS_BY_KIND.get(self.backend.kind, []), show_hidden=False)`. Stage A of v1.2.0 (`PLAN_KITTY_PARITY.md`, commit `f363beb`) already removed the `isinstance(AlacrittyBackend)` guard, so this path runs for both backends. |
| 3 | `src/ztc/screens/terminal_settings.py` (`action_import`, **confirmed exists** at line ~270) | Same change as #2, with the same shared `IMPORT_EXTENSIONS_BY_KIND` mapping. |
| 3.5 | `src/ztc/services/terminals/__init__.py` | Add a module-level constant `IMPORT_EXTENSIONS_BY_KIND: dict[str, list[str]] = {"alacritty": [".toml"], "kitty": [".conf"]}`. Single source of truth used by both screens. Adding a new backend later means adding one entry here, not editing each screen. |
| 4 | `src/ztc/widgets/confirm.py` (`PaneEditModal`) | Add a "Find" Button to the right of the Command Input. **Use the same `.field` sub-container pattern that landed in v1.1.0** — embed Input + Button inside `Horizontal(classes="field")` with `dock: right` on the Button so the Input keeps its visible right border. On click, open picker with `initial_dir=Path.cwd()`, `initial_value=current_command`, `allow_empty=True`, `extensions=None`, `show_hidden=True`. Existing free-text behavior in the Input stays untouched. |
| 5 | `tests/test_file_picker.py` (new) | Modal opens at `initial_dir`; tree filters by `extensions`; tree hides/shows hidden files per `show_hidden`; tree-selecting updates the Input; Confirm dismissal returns the Input value; Cancel returns None; `allow_empty=False` blocks Confirm with empty input; manual typing without browsing also confirms. |
| 6 | `tests/test_color_editor_screen.py` (currently empty) | Add import-flow tests covering the new picker integration: action_import opens FilePickerModal with the right params; confirming with a valid path triggers the import; cancel does nothing. |
| 7 | `tests/test_terminal_settings_screen.py` | Add equivalent import-flow tests (no specific import tests exist there today). |
| 8 | `tests/test_layout_editor_screen.py` | New test: clicking "Find" in `PaneEditModal` pushes the picker with the expected params; selecting a file fills the Command field; `allow_empty=True` for that path lets the user save the modal with empty Command. |

## Design decisions

- **Always-visible tree** in the modal. No "Find" button to expand —
  the tree is part of the modal layout from the start. Simpler to
  implement, no toggle state. Modal is bigger, but `PaneEditModal`
  is already 80×24-ish; the picker fits.

- **Default path per use case** (the only difference between callers):
  - **Import flow**: backend's config dir (`~/.config/alacritty/`).
  - **Pane command**: `Path.cwd()` evaluated at the moment the
    picker opens (not captured at app start). Simple, no extra
    state — the picker just resolves it lazily on demand.

- **Manual entry as first-class fallback**. The `Input` at the top
  is editable. The user can ignore the tree entirely and just type a
  command (`bash`) or a full path. Confirming applies whatever is in
  the `Input`, regardless of whether it matches a tree selection.

- **Tree selection updates Input** but the reverse is not true.
  Typing in the `Input` does NOT filter or scroll the tree — that
  would be autocomplete-ish, which is more complex and out of scope.
  Tree is for browsing; Input is for typing.

- **Extension filtering** (optional per call). The modal accepts a
  list like `[".toml"]` and hides files that don't match.
  Directories are always shown. If the list is `None`, all files
  are shown. For the pane command use case, no filter (any file
  may be an executable).

- **No existence/type/content validation in the modal**. The picker
  does not check whether the typed/selected path exists on disk,
  whether it points to a regular file vs a directory, or whether
  the file is parseable. That responsibility stays with the caller
  (e.g. `import_theme_file` raises `FileNotFoundError` for missing
  files; Zellij at runtime decides whether the pane command resolves).
  The **only** validation the picker enforces is the empty-or-not
  policy via `allow_empty` (see "Validation behavior" below).

## Out of scope

- **Autocomplete in the `Input`** (filtering the tree as the user
  types). Possible future enhancement; not needed for v1.3.0.
- **Multi-file selection**. Each call returns one path or `None`.
- **Recent paths history**. Maybe a future quality-of-life feature.
- **Pane command Input.Changed live preview** of executable validity.
  The picker just helps select; validation happens at Zellij run-time
  if the path is bad.

## Resolved decisions (previously open questions)

1. **Picker entry-point in `PaneEditModal`**: visible "Find" Button
   next to the Command Input. **No keybinding** — `ctrl+o` was
   considered but rejected (Zellij uses it for sessions and ZTC
   must run cleanly inside Zellij). A keybinding may be added later
   if the button feels insufficient.

2. **Extension filter for import**: **hardcoded per backend** —
   `.toml` for Alacritty, `.conf` for Kitty. Both backends are
   supported because Stage A of v1.2.0 (`PLAN_KITTY_PARITY.md`,
   commit `f363beb`) already landed the Kitty import capability.
   **Resolution pinned**: a single module-level constant
   `IMPORT_EXTENSIONS_BY_KIND` in `src/ztc/services/terminals/__init__.py`
   (`{"alacritty": [".toml"], "kitty": [".conf"]}`), looked up via
   `backend.kind` at the call site. No protocol method, no per-screen
   duplication. For pane command, no extension filter (any file may
   be an executable).

3. **`initial_dir` doesn't exist**: handled gracefully by the modal,
   no special caller logic needed. Frequency analysis:
   - **Pane command**: `Path.cwd()` always exists (process can't
     run otherwise). Case impossible.
   - **Import flow**: backend's config dir exists in normal operation
     (the user has Alacritty/Kitty configured). The case only arises
     in rare edge cases (fresh install with no custom config, weird
     config path overrides).
   - Behavior when it does happen: `DirectoryTree` renders an empty
     tree; the `Input` is still editable and the user can type a path
     manually. If this ever turns out to be confusing in practice, we
     add explicit handling — but anticipating it now is over-engineering.

4. **Modal dimensions**: same as other modals in `confirm.py` (80
   cells wide, height 90% or auto). Confirm during implementation
   that the tree fits comfortably.

5. **Hidden files**: **per-caller configurable** via `show_hidden`.
   Initial answer was "never show", but reviewing against real use
   cases changed the call:
   - **Import flow**: `show_hidden=False`. Config dirs
     (`~/.config/alacritty/`) don't typically have hidden subdirs
     worth navigating; their visible contents are themes.
   - **Pane command**: `show_hidden=True`. Common script locations
     are hidden: `~/.local/bin/`, `~/.bashrc.d/`, etc. The user's
     own retro boot-screen walkthrough wants
     `~/.bashrc.d/welcome-c64.sh` — hiding `~/.bashrc.d/` would
     break the very use case that motivates this feature.

   Hiding requires a `FilteredDirectoryTree(DirectoryTree)` subclass
   that overrides `filter_paths()` — Textual's stock `DirectoryTree`
   only styles hidden files differently, it does not filter them.

## Validation behavior — modeled as `allow_empty`

The earlier wording "no validation in the modal" contradicted "import
rejects empty" — corrected. The modal **does** apply one validation
policy: empty-or-not, controlled by `allow_empty: bool`. It does
**not** validate file existence, type or content — that is the
caller's responsibility (e.g. `import_theme_file` raises
`FileNotFoundError`).

- **Import flow**: `allow_empty=False`. Confirm button disabled when
  the Input is empty. Matches the prior `PromptModal` behavior.
- **Pane command**: `allow_empty=True`. An empty Command is a
  legitimate Zellij layout value (= "no command"). Confirm always
  enabled.

Cancel always dismisses with `None`. Confirm dismisses with
`Input.value` (a possibly-empty string when `allow_empty=True`).

## Acceptance criteria

- `uv run pytest -q` passes including new tests.
- `uv run ruff check` clean.
- Manual smoke test: open a color editor, press `i` for import →
  picker opens with config dir as initial path, can navigate, select
  a theme file, confirm → import succeeds.
- Manual smoke test: open a pane edit modal, click "Find" → picker
  opens, select a script, confirm → field is filled with the path.
- The Command field still works as before for free-text entry.

## Versioning

- Target version: **v1.3.0** (per ROADMAP).
- Single commit at the end of execution. Per the project rule, the
  bump to `1.3.0`, the `v1.3.0` tag and the GitHub Release are
  user-triggered after the work is committed and verified.

## Walkthrough doc

The retro 8-bit boot-screen walkthrough also targets v1.3.0 but is
**not** part of this plan — it lives in `doc/WALKTHROUGH_*.md` (TBD)
and uses the file picker (among other features) as one of the steps.
Will be planned and authored separately once the picker lands.
