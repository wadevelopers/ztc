# ztc

TUI en Python para administrar el setup de terminal: colores de la
terminal soportada y temas/layouts/sesiones de Zellij. Expone dos
comandos: `ztc` (app completa) y `zsm` (launcher de sesiones).

- [`doc/PLAN.md`](doc/PLAN.md) — diseno y roadmap del proyecto.
- [`doc/PLAN_MULTI_TERMINAL.md`](doc/PLAN_MULTI_TERMINAL.md) — spec de la
  arquitectura multi-terminal (vigente).
- [`doc/NOTES.md`](doc/NOTES.md) — gotchas operativos y notas de uso.

## Installation

```bash
uv tool install ztc
```

Instala dos comandos en `PATH`:

- `ztc`: app completa con menu (themes, layouts, sessions, terminal
  colors, terminal settings).
- `zsm`: launcher rapido de sesiones — equivalente a abrir `ztc` y elegir
  "Zellij sessions" desde el menu, pero sin pasar por el menu.

### Requisitos

- Python 3.11+.
- Zellij (opcional). Si no esta instalado, los items de Zellij en el menu
  aparecen disabled con la nota `(zellij not installed)`.
- Para edicion de colores y settings: Alacritty o Kitty configurados.
- Para selector de fuente en Terminal settings: `fontconfig` (fc-list).
  Sin el, el campo `font.family` cae a un input de texto libre.

## Usage

### `ztc` — app completa

Abre el menu con todas las features:

- **Zellij theme**: elegir/editar el tema activo de Zellij.
- **Zellij layouts**: gestionar layouts.
- **Zellij sessions**: launcher de sesiones (equivalente a `zsm` directo).
- **Terminal colors**: editar colores de Alacritty/Kitty sincronizados con
  el tema de Zellij.
- **Terminal settings**: editar padding, opacity, font size/family y
  cursor shape del backend activo. Mismos 6 settings funcionan en
  Alacritty (`alacritty.toml`) y Kitty (`kitty.conf`); el backend se
  encarga del formato propio. `font.family` ofrece un selector con
  las fuentes monoespaciadas detectadas via fontconfig.

Navegacion: `↑↓` mover, `↲` abrir, `q` salir.

### `zsm` — launcher rapido de sesiones

Abre directamente el selector de sesiones, sin pasar por el menu de ztc.
Util como reemplazo del shell-prompt-to-zellij: cada vez que abris una
terminal, ejecutas `zsm`, eligis attach/new/bash, y entras al destino.

Atajos dentro del selector: `enter` attach, `n` new, `l` new+layout,
`r` rename, `k` kill, `d` delete, `b` bash, `q` salir.

## Estado

En desarrollo. Soporte para edicion de colores en Alacritty y Kitty
con deteccion automatica de la terminal en uso.

## Terminales soportadas

| Terminal | Formato | Notas |
|---|---|---|
| **Alacritty** | TOML | Soporte completo + `import_theme_file` desde otro `alacritty.toml`. |
| **Kitty** | flat key/value | Soporte completo, incluyendo expansion de `include` para reflejar el estado efectivo. |

Ghostty queda diferida (ver Fase D futura en `doc/PLAN_MULTI_TERMINAL.md`).

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

## How it works

### `zsm` reemplaza su propio proceso al lanzar

Cuando elegis attach/new/bash en `zsm`, no se abre Zellij como un proceso
hijo — el comando usa `os.execvp` para **reemplazar** el proceso `zsm`
por Zellij. Visualmente:

```
shell (PID 100)
  └─ zsm (PID 200)         ← TUI corriendo
       │ elegis "attach mi-sesion"
       │ os.execvp("zellij", "attach", "mi-sesion")
       ↓
shell (PID 100)
  └─ zellij (PID 200)      ← MISMO PID, distinto programa
       │ trabajas en zellij
       │ cerras zellij
       ↓
shell (PID 100)            ← vuelve el control al shell
```

`zsm` no consume memoria mientras estas en zellij — fue literalmente
reemplazado, ya no existe como proceso.

### Misma logica para "Zellij sessions" desde `ztc`

Cuando elegis attach/new/bash desde el menu embebido de ztc, ztc se
reemplaza por Zellij con el mismo mecanismo. La unica diferencia es que
`cancel` (Esc/q) vuelve al menu de ztc en lugar de salir al shell.

### Limitacion: lanzar fuera de Zellij

Las operaciones attach a otra sesion y crear nueva requieren que el
proceso que las ejecuta **no este dentro de una sesion Zellij** — es una
restriccion de Zellij, no del launcher. El caso de uso primario de `zsm`
es ejecutarlo desde el shell antes de entrar a Zellij. Si lo invocas
desde un pane de Zellij existente, esas operaciones van a fallar.

## Desarrollo

```bash
uv venv
uv pip install -e ".[dev]"
uv run ztc       # app completa
uv run zsm       # launcher de sesiones
uv run pytest
```
