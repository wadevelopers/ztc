# Retro-style terminal showcase

This walkthrough recreates a classic 8-bit boot-screen feel using only
ZTC-managed terminal settings and a Zellij pane layout. It is a usage
example, not a new feature: the goal is to show how terminal color,
padding, pane background and a startup command compose into one look.

## Result

![Retro-style terminal showcase running with `bash` plus the C64 banner](screenshots/showcase.png)

- The terminal window uses a saturated blue background with extra
  padding, creating the outer frame.
- The focused Zellij pane uses a darker blue background and pale text,
  creating the inner screen.
- A tiny shell script prints a boot-style banner with terminal name,
  terminal version, Bash version and memory information.

## Font

The look works with any monospaced font. Two options:

- **A Nerd Font you already have** (for example
  `JetBrainsMono Nerd Font`) — nothing to install.
- **`C64 Pro Mono`** — closer to the real thing, but its glyphs are
  quite wide, so it needs a smaller `font.size` (and, to compensate,
  more `window.lines`) to keep the window a reasonable size. Install it:

  1. Download the `C64 TrueType` package from
     <https://style64.org/c64-truetype>.
  2. Install the monospaced TTF locally:

     ```bash
     mkdir -p ~/.local/share/fonts
     cp C64_Pro_Mono-STYLE.ttf ~/.local/share/fonts/
     fc-cache -fv
     fc-match "C64 Pro Mono"
     ```

  3. If `fc-match` prints a different family name, use that name as
     `font.family` in **Terminal settings** below.

## Terminal settings

In **Terminal settings**, apply the column for the font you picked.
Both columns end up with a terminal window of roughly the same size:

| Setting | JetBrainsMono Nerd Font | C64 Pro Mono |
|---|---|---|
| `window.columns` | `80` | `70` |
| `window.lines` | `25` | `47` |
| `window.padding.x` | `40` | `40` |
| `window.padding.y` | `40` | `40` |
| `window.opacity` | `1.0` | `1.0` |
| `font.size` | `12.0` | `9.0` |
| `font.family` | `JetBrainsMono Nerd Font` | `C64 Pro Mono` |
| `cursor.shape` | `Block` | `Block` |

> **Note:** changes to `window.columns` and `window.lines` require
> restarting the terminal to take effect.

## Terminal colors

In **Terminal colors**, set the terminal background to:

```text
#9190ef
```

This becomes the outer frame color. Accept Kitty's auto-reload prompt
if it shows up (optional — restarting the terminal works too).

## Banner script

Create this file:

```bash
mkdir -p ~/.config/ztc
$EDITOR ~/.config/ztc/welcome-c64.sh
```

Paste:

```bash
#!/usr/bin/env bash
# C-64-inspired welcome banner with terminal and memory info.

_c64_awk2() { "$@" 2>/dev/null | awk '{print $2; exit}'; }
_c64_ver() { "$@" 2>/dev/null | grep -oE '[0-9]+(\.[0-9]+){0,2}' | head -1; }

_c64_cols() {
    local size cols
    size=$(stty size </dev/tty 2>/dev/null) || size=
    cols=${size#* }
    [[ $cols =~ ^[1-9][0-9]*$ ]] && { printf '%s' "$cols"; return; }
    [[ ${COLUMNS:-} =~ ^[1-9][0-9]*$ ]] && { printf '%s' "$COLUMNS"; return; }
    printf '80'
}

_c64_center() {
    local pad=$(( ($1 - ${#2}) / 2 ))
    printf '%*s%s\n' "$(( pad < 0 ? 0 : pad ))" '' "$2"
}

_c64_terminal() {
    if [[ $TERM_PROGRAM == ghostty || $TERM == xterm-ghostty ]]; then
        term_name=GHOSTTY; term_ver=${TERM_PROGRAM_VERSION:-$(_c64_ver ghostty +version)}
    elif [[ -n $KITTY_WINDOW_ID || $TERM == xterm-kitty ]]; then
        term_name=KITTY; term_ver=$(_c64_awk2 kitty --version)
    elif [[ -n $ALACRITTY_LOG || $TERM == alacritty ]]; then
        term_name=ALACRITTY; term_ver=$(_c64_awk2 alacritty --version)
    elif [[ -n $GNOME_TERMINAL_SERVICE ]]; then
        term_name="GNOME TERMINAL"; term_ver=$(_c64_ver gnome-terminal --version)
    elif [[ -n $KONSOLE_VERSION ]]; then
        term_name=KONSOLE; term_ver=$KONSOLE_VERSION
    elif [[ $TERM_PROGRAM == WezTerm ]]; then
        term_name=WEZTERM; term_ver=$(_c64_awk2 wezterm --version)
    elif [[ -n $XTERM_VERSION ]]; then
        term_name=XTERM; term_ver=$(grep -oE '[0-9]+' <<<"$XTERM_VERSION" | head -1)
    elif [[ -n $VTE_VERSION ]]; then
        term_name=VTE; term_ver=$VTE_VERSION
    fi
}

welcome_c64() {
    local cols term_name=${TERM:-UNKNOWN} term_ver= line1 line2
    local total_kb avail_kb avail_bytes bash_ver
    cols=$(_c64_cols)

    _c64_terminal
    read -r total_kb avail_kb < <(awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} END{print t, a}' /proc/meminfo)
    avail_bytes=$(( avail_kb * 1024 ))
    bash_ver=${BASH_VERSION%%(*}

    line1="**** ${term_name} ${term_ver} BASH V${bash_ver} ****"
    line2="${total_kb}K RAM SYSTEM  ${avail_bytes} BYTES FREE"

    printf '\n'
    _c64_center "$cols" "$line1"
    printf '\n'
    _c64_center "$cols" "$line2"
    printf '\n'
    printf 'READY.\n'
}

if [[ -z ${WELCOME_SHOWN:-} ]]; then
    export WELCOME_SHOWN=1
    welcome_c64
fi

```

## Zellij layouts

Create or edit a Zellij layout in `ztc`, then configure the main pane:

| Pane field | Value |
|---|---|
| `default_bg` | `#2c2a80` |
| `default_fg` | `#9190ef` |
| `command` | `bash` |
| `args` | `-lc 'bash "$HOME/.config/ztc/welcome-c64.sh"; export PS1=""; exec bash --noprofile --norc -i'` |
| `borderless` | `true` |

Both `PS1=""` and `--noprofile --norc` only affect this pane — your
global shell prompt is not touched.

The equivalent KDL pane looks like:

```kdl
pane command="bash" borderless=true {
    default_bg "#2c2a80"
    default_fg "#9190ef"
    args "-lc" "bash \"$HOME/.config/ztc/welcome-c64.sh\"; export PS1=\"\"; exec bash --noprofile --norc -i"
}
```

Save the layout, launch it, and the pane should open with the banner
and an interactive shell.
