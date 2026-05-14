# Roadmap

ZTC follows [SemVer](https://semver.org/). Minor versions ship one
focused feature each — small, atomic releases instead of large
batches. Patch versions are bug-fix-only.

## Released

- **v1.3.0** — Terminal profiles via Load / Save. The color editor and
  terminal-settings editor support switchable profiles: **Save** (`s`)
  opens a modal prefilled with the active profile name, **Load** (`l`)
  reads a profile from disk and applies it live. Behind the scenes,
  the first Save with a new name converts the default config
  (`alacritty.toml` / `kitty.conf`) into a *manifest* that imports the
  active profile; subsequent saves and loads only rewrite the import
  line (Alacritty) or `include` line (Kitty), so global directives like
  `allow_remote_control` and `# ztc:` preferences stay in the manifest
  and survive profile switches. Live-reload follows: Alacritty picks up
  the manifest change via its watchdog; Kitty dispatches `kitty @
  load-config` and, for opacity, an idempotent `set-background-opacity`
  IPC after every switch. The old `Import` action (which merged colors
  / settings into the current doc) is gone — the manifest layer is the
  new merge point. See the rewritten
  [retro-style terminal showcase](C64_SHOWCASE.md) for an end-to-end
  walkthrough that uses the new profile flow.
- **v1.2.0** — Kitty parity. Two things: (1) **Kitty theme + settings
  import** — the color editor and the terminal-settings editor accept
  `i` for import on the Kitty backend, matching Alacritty;
  `import_theme_file` is part of the `TerminalBackend` Protocol and
  both backends implement it. (2) **Kitty auto-reload after save** —
  when ZTC writes to `kitty.conf` it runs `kitty @ load-config` so the
  change shows up instantly. This needs Kitty's remote control
  reachable; inside Zellij that requires `allow_remote_control yes` and
  `listen_on unix:@ztc-{kitty_pid}` in `kitty.conf`. On startup ZTC
  detects when this isn't set and shows a one-time educational modal
  offering to add the directives (user then restarts Kitty) or dismiss
  the prompt — the dismissal is stored as a `# ztc:` comment line in
  `kitty.conf`. When remote control isn't reachable, the save still
  happens and the toast reminds the user to press `Ctrl+Shift+F5`.
  Also includes the
  [retro-style terminal showcase](C64_SHOWCASE.md), a descriptive
  walkthrough that combines existing terminal settings, Zellij pane
  colors and a local banner script. The showcase is documentation only,
  not a new feature.
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

## Possible future work (no committed timeline)

- **PyPI publish** as `ztc-tui`. The name `ztc` is taken, so the PyPI
  distribution name would differ from the GitHub repo and the CLI
  command (which stays `ztc`). Not committed; the repo is already
  installable via `uv tool install git+https://github.com/wadevelopers/ztc`.
- **Support for more terminals.** Currently supported: Alacritty and
  Kitty. The backend layer in `src/ztc/services/terminals/` is built
  to be extended — implementing `TerminalBackend` for a new terminal
  (e.g. Ghostty, WezTerm, Foot) integrates it without touching the
  rest of the code. Fork contributions are welcome.
- **Reusable file picker.** The `Load` / `Save` flow in the terminal
  editors and the pane `command` field in the layout editor currently
  ask for a typed filesystem path. A `FilePickerModal` based on
  Textual's `DirectoryTree` would replace both with browsing, keeping
  free text for `$PATH` lookups. Fork contributions welcome.

## How to propose features or report bugs

Open an issue: <https://github.com/wadevelopers/ztc/issues>
