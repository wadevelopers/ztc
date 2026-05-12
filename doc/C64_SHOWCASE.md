# C-64-Inspired Terminal Showcase

This walkthrough recreates a classic 8-bit boot-screen feel using only
ZTC-managed terminal settings and a Zellij pane layout. It is a usage
example, not a new feature: the goal is to show how terminal color,
padding, pane background and a startup command compose into one look.

No proprietary logos, fonts or ROM assets are used. The style is only
inspired by the familiar blue/purple 8-bit terminal palette.

## Result

- The terminal window uses a saturated blue background with extra
  padding, creating the outer frame.
- The focused Zellij pane uses a darker blue background and pale text,
  creating the inner screen.
- A tiny shell script prints a boot-style banner with terminal name,
  terminal version, Bash version and memory information.

## Terminal Settings

Open `ztc`, then go to **Terminal settings** and set:

| Setting | Value |
|---|---|
| `window.padding.x` | `10` |
| `window.padding.y` | `4` |
| `window.opacity` | `1.0` |
| `cursor.shape` | `Block` |

Optional font setup:

1. Download the `C64 TrueType` package from
   <https://style64.org/c64-truetype>.
2. Install the monospaced TTF locally:

   ```bash
   mkdir -p ~/.local/share/fonts
   cp C64_Pro_Mono-STYLE.ttf ~/.local/share/fonts/
   fc-cache -fv
   fc-match "C64 Pro Mono"
   ```

3. In **Terminal settings**, set:

   | Setting | Value |
   |---|---|
   | `font.family` | `C64 Pro Mono` |
   | `font.size` | `16` |

If `fc-match` prints a different family name, use that exact name in
`font.family`.

Then go to **Terminal colors** and set the terminal background to:

```text
#4040e0
```

This becomes the outer frame color. On Kitty, ZTC may offer to add
the reload settings needed for live updates. Accepting them is optional
for the showcase; restarting the terminal after saving always works.

For Alacritty, set a compact window size in `alacritty.toml`:

```toml
[window.dimensions]
columns = 80
lines = 25
```

## Banner Script

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
_c64_center() { printf '%*s%s\n' "$(( ($1 - ${#2}) / 2 ))" '' "$2"; }

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
    local cols=80 term_name=${TERM:-UNKNOWN} term_ver= line1 line2
    local total_kb avail_kb avail_bytes bash_ver
    cols=$(tput cols 2>/dev/null || printf '80')

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

This file lives under `~/.config/ztc`, not under `~/.bashrc.d`, so it
is not loaded by normal interactive shells that source every script in
`~/.bashrc.d`.

## Zellij Layout

Create or edit a Zellij layout in `ztc`, then configure the main pane:

| Pane field | Value |
|---|---|
| `command` | `bash` |
| `args` | `-lc 'bash "$HOME/.config/ztc/welcome-c64.sh"; export PS1=""; exec bash --noprofile --norc -i'` |
| `default_bg` | `#0000aa` |
| `default_fg` | `#8080ff` |
| `borderless` | `true` |

Use `bash` plus `args` instead of putting the script path directly in
`command`: Zellij does not expand `~` in `command`, while `bash -lc`
does expand `$HOME` inside the argument string. Running the script with
`bash "$HOME/..."` also means the file does not need executable
permissions.

The `export PS1=""` part removes the interactive prompt only inside
that pane, keeping the retro `READY.` look without changing your
global shell prompt. The shell is started with `--noprofile --norc`
so your regular `.bashrc` does not overwrite the empty prompt.

The equivalent KDL pane looks like:

```kdl
pane command="bash" borderless=true {
    args "-lc" "bash \"$HOME/.config/ztc/welcome-c64.sh\"; export PS1=\"\"; exec bash --noprofile --norc -i"
    default_bg "#0000aa"
    default_fg "#8080ff"
}
```

Save the layout, launch it, and the pane should open with the banner
and an interactive shell.

## Tweaks

- Increase `window.padding.x` and `window.padding.y` for a thicker
  frame.
- Use `#2020c0` for a darker outer frame or `#5050ff` for a brighter
  one.
- Use `#a0a0ff` for a brighter pane foreground if your theme has low
  contrast.
