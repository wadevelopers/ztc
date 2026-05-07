# NOTES — cosas a saber al usar ztc

Notas operativas que no son obvias mirando solo el codigo. Conviene leerlas
antes de la primera vez para no llevarte sorpresas.

---

## 1. Antes de la primera ejecucion

### Fuente con iconos (Nerd Font)

Los iconos de la status-bar y tab-bar de Zellij son glifos de
[Nerd Fonts](https://www.nerdfonts.com). Si la terminal donde corres `zellij`
no usa una Nerd Font, veras cuadros vacios o rectangulos.

- En Alacritty ya esta configurado (`JetBrainsMono Nerd Font` en
  `~/.config/alacritty/alacritty.toml`).
- En GNOME Terminal hay que cambiarlo a mano: Preferencias -> tu perfil
  -> Texto -> Custom font -> `JetBrainsMono Nerd Font`.
- Para instalar la fuente si no esta:
  ```bash
  mkdir -p ~/.local/share/fonts
  curl -fLO https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.zip
  unzip JetBrainsMono.zip -d ~/.local/share/fonts/JetBrainsMono
  fc-cache -fv
  ```

### Donde lanzar el TUI

Funciona desde cualquier terminal, pero **conviene lanzarlo fuera de una
sesion de Zellij** si quieres hacer attach o crear sesiones nuevas. Desde
dentro de zellij solo podras gestionar sesiones (kill / delete) — no
attach ni new.

Para detacharte de la sesion actual de zellij sin matarla: `Ctrl+O` y luego
`d`.

---

## 2. Atajo `p` para la paleta de comandos

Anadi un binding `p` que abre la paleta de comandos (lo mismo que `Ctrl+P`).

Solo se dispara **cuando no hay un Input con foco**. Cuando estas escribiendo
dentro de un modal (nombre de tab, hex de color, confirmacion por nombre, etc.)
la `p` se va al Input como letra normal — exactamente lo que quieres.

`Ctrl+P` tambien sigue funcionando.

---

## 3. Sesiones de Zellij

### Attach a una sesion

`Enter` sobre una sesion suspende el TUI, libera la TTY a `zellij attach`
y, cuando salgas o detaches de la sesion, el TUI vuelve.

**Bloqueado dentro de zellij**: si lanzaste el TUI desde un pane de Zellij,
attach te avisa y no hace nada. Detach (`Ctrl+O d`), sal del wrapper de
zellij, y vuelve a lanzar el TUI desde la terminal directamente.

### Resucitar una sesion exited

Cuando ves una sesion marcada `[exited]` (con `(EXITED - attach to resurrect)`
en el `raw_line`), `Enter` tambien funciona: la resucita usando el layout
guardado por Zellij.

**Importante**: solo se recrea el layout (paneles, posiciones, comandos).
Los procesos que estaban corriendo dentro **no** se reinician
automaticamente — los paneles arrancan vacios o con el comando declarado en
el layout, segun el caso.

Para borrarla definitivamente y que ya no se pueda resucitar: `x`.

### La sesion donde corre el TUI

Aparece marcada con `*` y queda **protegida**:
- `k` (kill) y `X` (delete --force) la rechazan con notificacion.
- `x` (delete sin force) si lo permite, pero fallara mientras este viva.

Esto es para no matarte tu propia terminal por error.

### Crear sesiones

- `n`: pide nombre, suspende TUI y lanza `zellij -s <name>`.
- `l`: pide nombre + layout opcional (te muestra los disponibles como hint),
  lanza `zellij -n <layout> -s <name>`.

Tambien bloqueadas dentro de zellij.

### Acciones destructivas: confirmacion por nombre

`k`, `x` y `X` abren un modal que **exige escribir el nombre exacto** de la
sesion. El boton "Borrar" sigue deshabilitado hasta que coincida. Es el
mecanismo de seguridad principal para evitar borrados por error.

---

## 4. Tema de Zellij

### Built-in vs user

- **Built-in** (dracula, tokyo-night, etc.): Zellij los resuelve por
  nombre en runtime. El TUI no puede previsualizar sus colores porque no
  estan en tu archivo. Solo ves el nombre.
- **User** (los definidos en el bloque `themes { ... }` de tu `config.kdl`):
  el TUI los detecta y muestra swatches reales con los colores.

### Edicion del config.kdl

El cambio de tema es **una sola linea** (`theme "..."`). El TUI lo
modifica con regex dirigida — el resto del `config.kdl` se preserva tal
cual: comentarios, indentacion, todo.

Si la directiva `theme` no existe en tu archivo, se anade al final.

### Reglas de extraccion de paleta (built-in -> legacy fg/bg/red/...)

Para sincronizar Alacritty y para clonar built-ins a user themes editables,
el TUI extrae una paleta legacy desde el formato nuevo de Zellij. Las
reglas estan validadas contra la conversion inversa oficial de Zellij
(impl `From<Palette> for Styling` en `zellij-utils/src/data.rs`). Una
sola regla por slot, sin condicionales por tema, sin overrides:

| Slot legacy | Origen en el .kdl |
|---|---|
| `bg` | `text_unselected.background` |
| `black` | `text_unselected.background` (= bg; Zellij usa `palette.black` como bg de plugins) |
| `fg` | `ribbon_unselected.background` (`palette.fg` en la conversion) |
| `white` | `text_unselected.base` |
| `red` | `exit_code_error.base` |
| `green` | `exit_code_success.base` |
| `yellow` | `table_title.emphasis_0` |
| `blue` | `ribbon_selected.emphasis_3` |
| `magenta` | `frame_highlight.emphasis_0` |
| `cyan` | `text_unselected.emphasis_1` |
| `orange` | `text_unselected.emphasis_0` |

Algunos temas (dracula, ao, cyber-noir, etc.) tienen
`text_unselected.background = "#000000"` como placeholder de "usa el
bg del terminal". Para esos, el bg derivado cae a `#000000` (negro puro).
Es el dato crudo del .kdl tal cual. No hay heuristica oculta.

### Lista de built-in en el picker

`BUILTIN_THEMES` no es una lista hardcodeada: se deriva en runtime de
los archivos `.kdl` vendorizados en `src/ztc/assets/zellij_themes/`.
Hoy son **40 temas** (los 41 del repo de Zellij menos `ansi`, que usa
indices de paleta del terminal en vez de RGB y no podemos construir un
Textual Theme desde el).

Si Zellij agrega un tema nuevo en una version posterior, basta con
descargar su `.kdl` al directorio assets y aparece automaticamente en
el picker.

### Sincronizacion automatica con Alacritty al cambiar de tema

Cada vez que aplicas un tema en el Theme Picker (Enter), el TUI tambien
sincroniza estos slots de `alacritty.toml`:

| Slot Zellij | Slot Alacritty |
|---|---|
| `fg` | `[colors.primary] foreground` |
| `bg` | `[colors.primary] background` |
| `black` | `[colors.normal] black` |
| `red` | `[colors.normal] red` |
| `green` | `[colors.normal] green` |
| `yellow` | `[colors.normal] yellow` |
| `blue` | `[colors.normal] blue` |
| `magenta` | `[colors.normal] magenta` |
| `cyan` | `[colors.normal] cyan` |
| `white` | `[colors.normal] white` (ademas `[colors.primary] foreground`) |

Y desde el formato nuevo de Zellij:

| Slot Zellij (rich) | Slot Alacritty |
|---|---|
| `text_selected.background` | `[colors.selection] background` |
| `text_selected.base` | `[colors.selection] text` |

Para temas built-in todo se deriva del .kdl vendorizado. Para user
themes, se leen los slots del bloque `themes { }` (legacy + componentes
ricos). Si un slot no esta definido en el origen, no se toca en
Alacritty (preserva lo que tengas).

`[colors.bright]`, `[colors.cursor]` y todas las demas secciones
(`[window]`, `[font]`, etc.) **no se tocan**. Despues de sincronizar
puedes seguir editando manualmente desde Colores Alacritty.

Solo se escribe si hay cambios efectivos. Si el slot ya tenia el valor
correcto, no genera diff ni backup. Cuando sí escribe, crea el backup
habitual `alacritty.toml.bak.YYYYMMDD-HHMMSS`.

### Sincronizacion con el tema del propio TUI (match exacto)

Al arrancar, el TUI:

1. Carga los 41 temas built-in de Zellij vendorizados en
   `src/ztc/assets/zellij_themes/` (descargados del repo
   oficial, MIT).
2. Construye un Textual `Theme` desde cada uno, mapeando los slots
   del formato nuevo (`text_unselected.background`, `ribbon_selected.
   background`, `exit_code_error.base`, etc.) a los tokens de Textual
   (`background`, `primary`, `error`, ...).
3. Hace lo mismo con tus user themes legacy (`fg`, `bg`, `red`, ...)
   leidos de `config.kdl`.
4. Lee `theme "..."` de tu config y aplica el Textual con el **mismo
   nombre**. Cada Zellij theme tiene su match exacto: `dracula` en
   Zellij -> `dracula` en el TUI con los hex reales del repo.

Esto significa que:

- Clonar un built-in (`c` en el theme picker) crea un user theme con
  los colores reales extraidos del .kdl vendorizado, no con `#000000`.
- Editar / clonar un user theme refresca el registro en Textual al
  guardar, asi que el TUI usa los nuevos hex sin reiniciar.
- El tema `ansi` esta excluido del registro porque usa indices de
  paleta del terminal (0..15), no RGB. Si lo activas en Zellij, el
  TUI cae al fallback `textual-dark`.
- Si Zellij saca un tema nuevo que no este vendorizado aqui, el TUI
  cae al fallback hasta que actualicemos los assets.

### Clonar el tema activo preserva tweaks de Alacritty

Cuando clonas el **tema actualmente activo** desde el Theme Picker (`c`),
los slots actuales de `alacritty.toml` (fg, bg, 8 normales) se overlayan
sobre los derivados del .kdl. Asi el clon refleja exactamente lo que ves
en pantalla, incluyendo cualquier ajuste manual que hayas hecho en el
editor de Colores Alacritty desde el ultimo apply.

Si clonas un tema **distinto al activo**, no se aplica overlay (tendria
sentido, alacritty representa el tema activo, no el clonado). Vienen
solo los slots derivados del .kdl.

El slot `orange` (que no esta en alacritty) siempre viene del .kdl
como fallback.

### Custom themes (crear / editar / clonar / borrar)

Desde el Theme Picker:

| Tecla | Accion |
|---|---|
| `n` | Nuevo user theme (pide nombre, abre editor) |
| `e` | Editar el user theme seleccionado |
| `c` | Clonar el seleccionado bajo nuevo nombre |
| `d` | Borrar user theme (confirm-by-name) |

Al clonar un built-in, el clon hereda **toda** la informacion del .kdl
original: la paleta legacy (11 slots) y los componentes del formato
nuevo de Zellij (text_selected, ribbon_selected, etc.). Asi el clon
renderiza igual que el built-in en Zellij.

### Editor de user themes

El editor muestra dos secciones:

- **Paleta ANSI**: los 11 slots legacy (`fg`, `bg`, `black`, `red`,
  `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`, `orange`).
  Mapean a `colors.primary.*` y `colors.normal.*` de Alacritty.
- **UI (Zellij)**: 4 slots ricos del formato nuevo:
  - `text_selected.background` → `colors.selection.background` de
    Alacritty (color de fondo cuando seleccionas texto).
  - `text_selected.base` → `colors.selection.text`.
  - `ribbon_selected.background` → bg del tab activo de Zellij.
  - `ribbon_selected.base` → texto del tab activo.

**Atajos en el editor:**

| Tecla | Accion |
|---|---|
| `Enter` | Editar el slot seleccionado (modal con preview) |
| `x` | Resetear el slot (eliminar la asignacion del theme) |
| `s` | Guardar al config.kdl |
| `Esc` | Volver (con confirm si hay cambios sin guardar) |

Otros componentes del formato nuevo no expuestos en el editor (ej.
`frame_highlight`, `exit_code_*`, etc.) se **preservan opacos** en
`raw_components`: viajan con el clon pero no se editan desde el TUI.
Zellij los usa al renderizar.

**Limitacion**: comentarios `//` y `/-` dentro del bloque themes se
pierden al re-escribir el archivo. Si tienes anotaciones importantes
ahi, ponlas fuera del bloque.

---

## 5. Layouts de Zellij

### Que se preserva al guardar

- Tabs, paneles, propiedades (`size`, `command`, etc.) se serializan
  desde el modelo. Limpio.
- Nodos no entendidos (`default_tab_template`, `plugin location=...`,
  etc.) se guardan en `raw_unknown_nodes` y se re-emiten via la libreria
  KDL al guardar. El layout aparece marcado con `(+raw)` en la lista para
  que sepas que tiene esto.

### Lo que se pierde al guardar

- **Comentarios `/-` (slashdash)**: la libreria KDL que uso (`kdl-py`)
  no los expone al parsear, asi que desaparecen al re-escribir. Tu
  `dev.kdl` tiene un `tab-bar` desactivado con `/-` que se perderia si
  lo guardas desde el editor. Si necesitas mantenerlo, edita ese archivo
  a mano.
- **Comentarios normales `//`**: tambien se pierden, mismo motivo.
- **Formato exacto** (espacios, alineacion): el editor reformatea con
  4 espacios de indentacion. Semanticamente identico, visualmente puede
  diferir.

### Edicion en el editor

- `a` anade pane hermano, `s` parte el seleccionado en dos, `d` lo borra.
- `e` abre el modal de edicion: solo te muestra los campos relevantes
  segun sea hoja (command, args, cwd, etc.) o contenedor (split_direction).
- `J/K` mueven entre hermanos, `>/<` cambian el `size` en pasos de 5%
  (clamp 5..95%, solo aplica si el size esta en porcentaje).
- `Ctrl+S` guarda. `Esc` vuelve; si hay cambios sin guardar pide confirmar.

### Crear sesion con layout recien editado

El plan original mencionaba ofrecer "abrir/recrear sesion" justo despues
de guardar. Eso no esta implementado todavia: para usar tu layout
modificado, tienes que ir al **Session Manager** y crear una nueva sesion
con `l` (Nueva c/ layout), o matar la sesion existente y volver a
crearla con el mismo nombre + `l`.

---

## 6. Colores de Alacritty

### Avisos de contraste

El editor calcula contraste WCAG entre pares relevantes y avisa cuando son
problematicos:

| Caso | Umbral | Por que importa |
|---|---|---|
| `foreground` vs `background` | < 4.5 | Recomendacion WCAG para texto |
| `background` vs `normal.black` | < 1.5 | Apps que usen color "black" sobre el fondo se vuelven invisibles |
| `background` vs zellij bg | < 1.3 | Las barras de Zellij no se ven |
| `selection.background` vs `background` | < 1.3 | La seleccion no se distingue |
| `cursor.cursor` vs `background` | < 2.0 | Cursor dificil de localizar |

El cruce con el bg de Zellij solo funciona si el tema activo es **user**
(definido en tu `config.kdl`) y tiene un slot `bg`. Para temas built-in
no hay forma de saber el color sin hardcodearlo.

### Importar tema

`i` pide la ruta de otro `alacritty.toml`. Lee solo los slots conocidos
con valores hex validos y los sobreescribe en tu doc en memoria
(no toca otras secciones del destino). Si quieres conservar el archivo
original como fuente reusable, en vez de importar conviene anadirlo al
array `import` de Alacritty manualmente — el TUI tiene la funcion
`add_import` pero todavia no esta expuesta en la UI.

### Validacion de hex

El modal de edicion acepta `#rgb`, `#rrggbb` y `#rrggbbaa`. Mientras
escribes, ves el swatch en vivo y el boton "Guardar" se habilita solo
cuando el valor es valido. La normalizacion lo guarda en minusculas y
con `#`.

---

## 7. Backups

Antes de cualquier escritura sobre un archivo existente se crea una copia:

- `~/.config/zellij/config.kdl.bak.YYYYMMDD-HHMMSS`
- `~/.config/alacritty/alacritty.toml.bak.YYYYMMDD-HHMMSS`
- `~/.config/zellij/layouts/<name>.kdl.bak.YYYYMMDD-HHMMSS`

Para restaurar:
```bash
cp ~/.config/zellij/config.kdl.bak.20260502-150407 ~/.config/zellij/config.kdl
```

Los backups **no** se borran solos. Si te molestan al cabo del tiempo:
```bash
find ~/.config/zellij ~/.config/alacritty -name "*.bak.*" -mtime +30 -delete
```

---

## 8. Atomicidad de escritura

Cada `write` se hace via `mkstemp` + `os.replace` en el mismo directorio:
si la app crashea a mitad de escritura, no te quedas con un archivo
medio escrito. O queda el original intacto, o queda el nuevo completo.

---

## 9. Comandos utiles

```bash
# Lanzar el TUI
uv run ztc

# Tests
uv run pytest

# Lint
uv run ruff check .

# Instalar como CLI global (binario en ~/.local/bin/ztc)
uv tool install .
# o sin uv:
pipx install .
```

---

## 10. Limitaciones conocidas (resumen)

- Comentarios `//` y `/-` en layouts se pierden al guardar.
- Themes built-in de Zellij no se previsualizan (solo nombre).
- Cruce de contraste con Zellij solo funciona para temas user.
- "Recrear sesion con layout actualizado" no esta automatizado: hay que
  matar y recrear a mano desde el Session Manager.
- Undo/redo en el editor no esta implementado (Fase 5 pendiente).
