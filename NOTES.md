# NOTES — cosas a saber al usar term-config-tui

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
uv run term-config-tui

# Tests
uv run pytest

# Lint
uv run ruff check .

# Instalar como CLI global (binario en ~/.local/bin/term-config-tui)
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
