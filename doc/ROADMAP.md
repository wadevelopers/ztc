# Roadmap

ZTC follows [SemVer](https://semver.org/). Minor versions ship one
focused feature each — small, atomic releases instead of large
batches. Patch versions are bug-fix-only.

## v1.1.0 (next)

- **Editable pane background and foreground colors in the layout
  editor.** Zellij supports `default_bg` and `default_fg` per pane,
  giving complete visual control of a panel without touching
  terminal colors. Today these directives are partially preserved
  by ZTC (child-node form roundtrips, property form is silently
  dropped) and never editable from the TUI. v1.1.0 promotes both
  to first-class fields in the model, makes them editable from
  `PaneEditModal`, and adds visual swatches in the pane tree
  consistent with the sessions detail view. See
  [`PLAN_PANE_DEFAULT_BG.md`](PLAN_PANE_DEFAULT_BG.md).

## v1.2.0

- **Terminal startup command.** Allow defining a command (or script)
  that runs every time a new terminal session is opened. Auto-detect
  scripts in `~/.bashrc.d/` and offer them as a list, with the
  option to point at a specific script or write a literal command.
  Ships with a **"Commodore 64 terminal" walkthrough** in the docs
  as showcase: combines the pane bg/fg from v1.1.0 with a custom
  welcome banner via this startup command, producing a retro
  C64-styled terminal end-to-end.

## v1.3.0

- **File picker for theme/settings imports.** Today the importer
  takes a typed filename (resolved against the backend's config
  directory) or an absolute path. Both work but force the user to
  remember filenames. Add a visual picker that lists the config
  files already in the backend's directory (e.g. `.toml` files in
  `~/.config/alacritty/`, `.conf` files in `~/.config/kitty/`),
  with a fallback to manual path entry for files outside that
  directory. Open design question for the implementation: list-only
  with a separate "type a path" action, or hybrid with
  autocomplete-style input filtered by the list. To decide when
  drafting the plan.

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
