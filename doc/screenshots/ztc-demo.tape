# ztc demo — clone a theme, edit its background, jump to sessions
# Run: vhs doc/screenshots/ztc-demo.tape
# Output: doc/screenshots/ztc-demo.gif

Output doc/screenshots/ztc-demo.gif

# ---- Output dimensions tuned for GitHub README rendering ----
# 1200x700 fits the GitHub content column (~900 px) gracefully,
# stays readable on retina, and keeps the GIF under ~1.5 MB.
Set Shell "bash"
Set FontSize 18
Set Width 1200
Set Height 700
Set Padding 30
Set Theme "Dracula"
Set TypingSpeed 60ms
# 24 fps is plenty for a TUI demo (very few pixels change per frame)
# and cuts the GIF size by ~40% vs the default 50 fps.
Set Framerate 24

# vhs runs the TUI inside ttyd, so Alacritty/Kitty env markers aren't
# present and ztc would tag terminal-related menu items as
# "(unsupported)". Force the backend so the menu looks clean.
Env TERM_CONFIG_TUI_BACKEND "alacritty"

# ---- Hide setup + launch: GIF starts already inside ztc ----
# vhs uses non-interactive bash so ~/.bashrc isn't sourced and ztc isn't
# on PATH. Running via `uv run` from the project dir avoids needing a
# global install and keeps the demo reproducible from a fresh checkout.
# We also hide the launch itself so the recording opens on the main menu.
Hide
Type "cd /home/martin/Documents/ztc"
Enter
Type "clear"
Enter
Type "uv run ztc"
Enter
Sleep 3s
Show

# ---- Main menu visible from the very first frame. ----
# Hold ~1.7s on the menu so the viewer can read the options
# before navigation kicks in.
Sleep 1700ms
Enter
Sleep 1500ms

# ---- Theme list. Cursor on the active theme. Clone it. ----
Type "c"
Sleep 700ms

# Prompt modal. Type the new theme name.
Type "demo-c64"
Sleep 400ms
Enter
Sleep 1500ms

# After clone the cursor stays on the source theme.
# Navigate down a few times to reach demo-c64 (user themes
# usually live near the bottom of the list).
Down
Down
Down
Down
Sleep 500ms

# Apply the cloned theme so changes are live in the terminal.
Enter
Sleep 1500ms

# Edit it.
Type "e"
Sleep 1500ms

# Custom theme editor. Cursor lands on the first slot ("fg").
# "bg" is the slot right below.
Down
Sleep 400ms
Enter
Sleep 800ms

# EditColorModal appears with the current value pre-filled.
# Clear it (generous count covers any current value length)
# and type the new color.
Backspace 10
Type "#6272a4"
Sleep 400ms
Enter
Sleep 1500ms

# Save — this propagates to the active terminal in real time.
Type "s"
Sleep 2s

# Back to the theme list, then to the main menu.
Escape
Sleep 700ms
Escape
Sleep 1s

# Navigate to "Zellij sessions" (third menu item).
Down
Down
Sleep 400ms
Enter
Sleep 2s

# Sessions picker. Press `l` to start "New +layout".
Type "l"
Sleep 2500ms

# Layout picker is on screen — end the recording here.
