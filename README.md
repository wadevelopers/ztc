# ztc

TUI en Python para administrar el setup de terminal: colores de la
terminal soportada y temas/layouts/sesiones de Zellij.

- [`PLAN.md`](PLAN.md) — diseno y roadmap del proyecto.
- [`PLAN_MULTI_TERMINAL.md`](PLAN_MULTI_TERMINAL.md) — spec de la
  arquitectura multi-terminal (vigente).
- [`NOTES.md`](NOTES.md) — gotchas operativos y notas de uso.

## Estado

En desarrollo. Soporte para edicion de colores en Alacritty y Kitty
con deteccion automatica de la terminal en uso.

## Terminales soportadas

| Terminal | Formato | Notas |
|---|---|---|
| **Alacritty** | TOML | Soporte completo + `import_theme_file` desde otro `alacritty.toml`. |
| **Kitty** | flat key/value | Soporte completo, incluyendo expansion de `include` para reflejar el estado efectivo. |

Ghostty queda diferida (ver Fase D futura en `PLAN_MULTI_TERMINAL.md`).

## Como elige el backend la app

La app detecta automaticamente desde que terminal se la lanzo, mirando
env vars distintivas que sobreviven multiplexores como Zellij/tmux:

| Terminal | Marker |
|---|---|
| Alacritty | `ALACRITTY_WINDOW_ID` o `ALACRITTY_SOCKET` |
| Kitty | `KITTY_PID`, `KITTY_WINDOW_ID`, o `TERM=xterm-kitty` |

Si la terminal no es soportada (gnome-terminal, iTerm2, etc.), la
opcion "Colores de terminal" aparece deshabilitada con `(no soportada)`.
Las funciones de Zellij siguen disponibles si Zellij esta instalado.

### Override por env var

```bash
TERM_CONFIG_TUI_BACKEND=alacritty ztc
TERM_CONFIG_TUI_BACKEND=kitty ztc
TERM_CONFIG_TUI_BACKEND=auto ztc    # default
```

Util para tests, multiplexores raros o casos donde la deteccion
automatica no acierta. Un valor invalido (`wezterm`, etc.) deshabilita
la edicion de colores con un toast explicando el problema.

### SSH

Si detecta `SSH_CONNECTION`, deshabilita la edicion de colores: el
archivo de config local de tu cliente no es accesible desde el host
remoto.

## Edicion de colores en Kitty con `include`

Si tu `kitty.conf` incluye un tema (`include themes/tokyonight.conf`),
la app lee los colores efectivos expandiendo el include. Cuando
modificas un color desde el editor:

1. La nueva linea se appendea **al final de tu `kitty.conf`** (el
   archivo principal).
2. Como kitty procesa el archivo top-to-bottom y aplica
   "last-occurrence-wins", la linea appendeada gana sobre el include.
3. El archivo de tema (`themes/tokyonight.conf`) **no se toca** —
   tu tema queda intacto.
4. Si despues cambias el include a otro tema, los colores que
   editaste siguen ganando (porque siguen al final del main). Para
   "volver al tema" en un slot editado, usa "Resetear slot" (`x`)
   en el editor: borra la linea del main y el include vuelve a ganar.

Limitacion: `globinclude` y `envinclude` no se expanden, solo
`include` directo. Includes anidados se permiten hasta profundidad 5.

## Desarrollo

```bash
uv venv
uv pip install -e ".[dev]"
uv run ztc
uv run pytest
```

## Instalacion

```bash
uv tool install .
# o
pipx install .
```
