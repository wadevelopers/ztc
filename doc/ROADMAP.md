# Roadmap

## v1.1.0 (next)

- **Pane background color in the layout editor.** The current editor
  lets you adjust margins, borders and names but not the background
  color. This is the missing piece for a layout to render with a
  complete visual look (without depending solely on the Zellij theme).

- **Terminal startup command.** Allow defining a command that runs
  every time a new terminal is opened, with auto-detection of scripts
  in `~/.bashrc.d/` plus the option to point at a specific one. Useful
  for ASCII banners, fastfetch, welcome scripts, etc.

- **Import from absolute path.** Today the theme/settings importer
  only lists files next to the backend's config file. Add the option
  to pick a file by absolute path from any directory, while keeping
  the listing as a shortcut.

- **"Commodore 64 terminal" walkthrough.** Step-by-step tutorial that
  combines the items above: padding, pane color, terminal background
  and welcome banner via startup command. End-to-end showcase of the
  full setup.

- **PyPI release.** Publish to PyPI under the package name `ztc-tui`
  (the name `ztc` is already taken). CLI commands stay as `ztc` and
  `zsm`.

## Later

- **Support for more terminals.** Currently supported: Alacritty and
  Kitty. The backend layer in `src/ztc/services/terminals/` is built
  to be extended — implementing `TerminalBackend` for a new terminal
  (e.g. Ghostty, WezTerm, Foot) integrates it without touching the
  rest of the code. Fork contributions are welcome.

## How to propose features or report bugs

Open an issue: <https://github.com/wadevelopers/ztc/issues>
