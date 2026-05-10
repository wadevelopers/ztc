# Roadmap

ZTC follows [SemVer](https://semver.org/). Minor versions ship one
focused feature each — small, atomic releases instead of large
batches. Patch versions are bug-fix-only.

## v1.2.0 (next)

### Feature

- **Reusable file picker widget.** A `FilePickerModal` that lists
  files from a configurable directory (with extension filtering
  and a fallback to manual path entry). Replaces the typed-path
  inputs in two places:
  - **Import of theme/settings** in the colors and terminal-settings
    editors. Today the importer asks for a filename (resolved
    against the backend's config dir) or an absolute path. The new
    picker lists the existing files (e.g. `.toml` in
    `~/.config/alacritty/`, `.conf` in `~/.config/kitty/`).
  - **Pane `command` field** in the layout editor. Today the user
    has to type the full path of an executable script. The picker
    lets them browse the filesystem; the field still accepts free
    text for commands resolved via `$PATH` (`bash`, `vim`, etc.).

### Showcase doc (not a feature)

- **Retro boot-screen walkthrough.** A use-case example, not a new
  ZTC feature. Combines features that already exist or land in
  v1.2.0 to recreate the visual style of a classic 8-bit boot screen
  (purple frame around a darker terminal area, a banner script that
  prints terminal identity — name, versions, memory, etc.). Pieces:
  - Terminal bg color + padding from v1.0.0
  - Pane `default_bg` / `default_fg` from v1.1.0
  - File picker (v1.2.0) for selecting the banner script in the
    pane's command field
  - A bash banner script (shown inline in the doc) that the user
    saves locally; no bundled assets in ZTC
  The walkthrough is purely descriptive — its purpose is to show
  how ZTC's existing features compose into a complete custom look.

## Released

- **v1.1.0** — Editable pane `default_bg` / `default_fg` in the layout
  editor. Both directives are now first-class `Pane` fields, editable
  from `PaneEditModal` with strict format validation. The tree
  expands leaves to show their attributes as child rows (with inline
  color swatches for the bg/fg fields), and the `pane` keyword is
  rendered with theme-accent color for visual hierarchy. Cursor
  navigation skips property rows so only actionable nodes (panes,
  root) receive keyboard focus.
- **v1.0.0** — First public release. Alacritty/Kitty color and settings
  editing, Zellij themes, layouts and sessions management; embedded
  and standalone (`zsm`) launcher.

## Later (no committed version yet)

- **PyPI publish** as `ztc-tui`. The name `ztc` is taken, so the
  PyPI distribution name will differ from the GitHub repo and the
  CLI command (which stays `ztc`). Will land in some future minor
  release once the project has a few more iterations under its belt.
- **Support for more terminals.** Currently supported: Alacritty
  and Kitty. The backend layer in `src/ztc/services/terminals/` is
  built to be extended — implementing `TerminalBackend` for a new
  terminal (e.g. Ghostty, WezTerm, Foot) integrates it without
  touching the rest of the code. Fork contributions are welcome.

## How to propose features or report bugs

Open an issue: <https://github.com/wadevelopers/ztc/issues>
