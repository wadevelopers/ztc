# term-config-tui — Plan

TUI en Python para configurar y administrar mi setup de terminal:

- Alacritty
- Zellij layouts
- Zellij themes
- Zellij sessions

La idea principal es no tener que recordar sintaxis KDL/TOML ni comandos de sesion de Zellij para tareas comunes.

El plan prioriza dos necesidades:

1. El TUI tambien debe servir para **ver, abrir, cerrar, borrar y recrear sesiones de Zellij**.
2. La escritura de archivos debe ser conservadora: preservar lo posible y no destruir configuracion que el TUI todavia no edita.

---

## Objetivo

Construir una herramienta local, instalable por `pipx`, que permita:

- Elegir rapidamente el tema de Zellij.
- Editar layouts de Zellij sin escribir KDL a mano.
- Editar colores de Alacritty sin memorizar slots TOML.
- Administrar sesiones de Zellij desde una interfaz clara.
- Aplicar cambios de layout sin tener que recordar comandos como `zellij delete-session main --force`.

---

## Alcance

### Lo que SI va a configurar

1. **Sesiones de Zellij**
   - Listar sesiones vivas.
   - Listar sesiones salidas/resurrectables si Zellij las muestra.
   - Conectarse a una sesion existente.
   - Crear una sesion nueva con nombre.
   - Crear una sesion nueva usando un layout.
   - Cerrar/matar una sesion viva.
   - Borrar una sesion resurrectable.
   - Forzar borrado de una sesion concreta cuando haga falta.
   - Recrear una sesion concreta despues de guardar un layout.

2. **Layouts de Zellij**
   - Crear/editar/borrar layouts.
   - Soportar multiples archivos en `~/.config/zellij/layouts/*.kdl`.
   - Crear/editar/borrar tabs.
   - Dentro de cada tab: arbol de paneles con splits recursivos.
   - Por cada panel hoja: `command`, `args`, `cwd`, `start_suspended`, `size`, `focus`, `name`, `borderless`.
   - Por cada contenedor: `split_direction`, `size`, hijos.
   - Reordenar tabs y paneles.
   - Preservar, cuando sea posible, nodos que la UI aun no edita.

3. **Tema de Zellij**
   - Elegir un tema embebido.
   - Actualizar `theme "..."` en `config.kdl`.
   - Preview de colores.
   - Mas adelante: crear/editar temas custom.

4. **Colores de Alacritty**
   - Importar un tema externo `.toml`.
   - Overrides por slot:
     - `colors.primary`
     - `colors.normal`
     - `colors.bright`
     - `colors.selection`
     - `colors.cursor`
   - Preview con muestras de apps simuladas.
   - Avisos de contraste y colores demasiado cercanos.

### Lo que NO va a configurar en v1

- Keybinds completos de Zellij.
- Plugins de Zellij salvo lo necesario para no romper layouts existentes.
- Fuente/tamano/padding de Alacritty.
- Configuracion de apps como btop, nvim, shells, etc.
- Sincronizacion perfecta de una sesion viva sin reiniciarla.

---

## Stack

- **Lenguaje**: Python 3.11+
- **Framework TUI**: Textual
- **KDL**: parser/emisor KDL, con una capa propia de adaptacion
- **TOML**: `tomlkit` para leer/escribir Alacritty preservando formato y comentarios
- **CLI Zellij**: llamadas a `zellij` mediante un servicio propio
- **Distribucion**: `pipx`

### Nota sobre Python y TOML

`tomllib` solo lee TOML y existe en stdlib desde Python 3.11. Como este proyecto necesita escribir `alacritty.toml`, se usara `tomlkit`.

### Nota sobre KDL

No se debe asumir que el parser KDL preserva comentarios y formato de forma perfecta. La estrategia sera:

- Para cambios pequenos en `config.kdl`, hacer ediciones dirigidas:
  - cambiar `theme "..."`;
  - insertar/actualizar bloques controlados por la app.
- Para layouts creados por la app, emitir KDL limpio desde el modelo.
- Para layouts existentes, parsear lo que se entiende y preservar nodos desconocidos cuando sea razonable.

---

## Arquitectura

```text
~/.config/alacritty/alacritty.toml       <- lee/escribe
~/.config/zellij/config.kdl              <- lee/escribe
~/.config/zellij/layouts/*.kdl           <- lee/escribe
zellij CLI                               <- lista/abre/cierra sesiones
                    ^
                    |
              [ Config Service ]
              [ Session Service ]
                    ^
                    |
              [ Domain Models ]
                    ^
                    |
              [ Textual App ]
              |-- MainMenu
              |-- SessionManager
              |-- LayoutEditor
              |-- ZellijThemeEditor
              |-- AlacrittyColorEditor
              `-- PreviewPanel
```

---

## Modelos de dominio

### Layouts

```python
@dataclass
class Pane:
    command: str | None = None
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    start_suspended: bool = False
    size: str | None = None
    focus: bool = False
    name: str | None = None
    borderless: bool = False
    children: list["Pane"] = field(default_factory=list)
    split_direction: Literal["vertical", "horizontal"] | None = None
    raw_unknown_nodes: list[object] = field(default_factory=list)

@dataclass
class Tab:
    name: str | None = None
    children: list[Pane] = field(default_factory=list)
    focus: bool = False
    cwd: str | None = None
    split_direction: Literal["vertical", "horizontal"] | None = None
    raw_unknown_nodes: list[object] = field(default_factory=list)

@dataclass
class Layout:
    name: str
    path: Path
    tabs: list[Tab] = field(default_factory=list)
    cwd: str | None = None
    raw_unknown_nodes: list[object] = field(default_factory=list)
```

Reglas:

- Un `Pane` con `children` es contenedor.
- Un `Pane` sin `children` es hoja.
- Un contenedor no debe tener `command`.
- Al partir una hoja, la hoja original pasa a ser un hijo.
- Si se eliminan todos los hijos de un contenedor, se convierte en hoja vacia.

### Sesiones

```python
@dataclass
class ZellijSession:
    name: str
    state: Literal["running", "exited", "unknown"]
    is_current: bool = False
    raw_line: str | None = None
```

Notas:

- Zellij puede tener mas de una sesion.
- Algunas sesiones pueden estar vivas.
- Otras pueden estar cerradas pero disponibles para resurrection.
- El parser de `list-sessions` debe ser tolerante porque el formato puede variar por version.

---

## Session Manager

Pantalla para manejar sesiones de Zellij:

```text
+-------------------------+------------------------------------------+
| Sesiones Zellij         | Acciones                                 |
|                         |                                          |
| > main        running   | Enter  conectar                         |
|   work        running   | n      nueva sesion                     |
|   old-dev     exited    | l      nueva con layout                 |
|                         | k      cerrar sesion viva               |
|                         | x      borrar sesion exited             |
|                         | r      recrear con layout actualizado   |
|                         | R      refrescar lista                  |
+-------------------------+------------------------------------------+
| Detalle                                                         |
| main esta viva. Si recreas la sesion, los procesos dentro se     |
| cerraran.                                                       |
+-----------------------------------------------------------------+
```

### Acciones

| Atajo | Accion |
|---|---|
| `Enter` | conectarse a la sesion seleccionada |
| `n` | crear sesion nueva |
| `l` | crear sesion nueva con layout |
| `k` | cerrar/matar sesion viva |
| `x` | borrar sesion exited/resurrectable |
| `r` | recrear sesion seleccionada con un layout |
| `R` | refrescar lista |
| `?` | mostrar ayuda corta |

### Comandos Zellij usados

El servicio no debe hardcodear una sola forma para todas las versiones. Debe detectar capacidades con `zellij --help` y `zellij <subcommand> --help`.

Operaciones esperadas:

- Listar:
  - `zellij list-sessions`
  - alias posible: `zellij ls`
- Conectar:
  - `zellij attach <session>`
- Crear:
  - `zellij --session <name>`
  - o la forma equivalente disponible en la version instalada
- Crear con layout:
  - `zellij --new-session-with-layout <layout> --session <name>`
  - o la forma equivalente disponible en la version instalada
- Cerrar sesion viva:
  - `zellij kill-session <session>`
  - o `zellij kill-sessions <session>` segun version
- Borrar sesion:
  - `zellij delete-session <session>`
- Forzar borrado/cierre:
  - `zellij delete-session <session> --force`
  - o `zellij delete-session --force <session>` si la version lo requiere

### Confirmaciones

Las acciones destructivas deben pedir confirmacion clara:

- Cerrar sesion viva.
- Borrar sesion.
- Borrar con `--force`.
- Recrear sesion.

Texto recomendado:

```text
Esto cerrara la sesion "main" y todos los procesos dentro.
Escribe el nombre de la sesion para confirmar: main
```

---

## Sincronizacion de layouts con sesiones

Un layout guardado no actualiza automaticamente una sesion viva que ya fue creada con una version anterior del layout.

Cuando el usuario guarda un layout, el TUI debe ofrecer:

1. Guardar solamente.
2. Abrir una sesion nueva con este layout.
3. Recrear una sesion existente con este layout.
4. Ir al Session Manager.

La opcion de recrear debe:

- listar sesiones existentes;
- permitir elegir una sesion concreta;
- advertir que se cerraran los procesos dentro;
- ejecutar el cierre/borrado necesario;
- crear una nueva sesion con el mismo nombre y el layout actualizado.

No debe asumir siempre que la sesion se llama `main`.

---

## Layout Editor

Pantalla con tres zonas:

```text
+------------------------+--------------------------------------------+
| Layouts / Tabs         | Tab seleccionado: dev                      |
|                        |                                            |
| layouts:               | Pane tree:                                 |
| > dev.kdl              | v split_direction: vertical                |
|   trabajo.kdl          |   |- Pane #1 [60%] command: nvim            |
|                        |   `- v horizontal [40%]                    |
| tabs:                  |      |- Pane #2 [70%] command: <shell>       |
| > system               |      `- Pane #3 [30%] command: btop        |
|   dev                  |                                            |
+------------------------+--------------------------------------------+
| Preview KDL generado                                                |
+---------------------------------------------------------------------+
```

### Operaciones del arbol de paneles

| Atajo | Accion |
|---|---|
| `a` | anadir panel hermano |
| `s` | partir panel seleccionado |
| `d` | borrar panel |
| `Enter` | editar propiedades |
| `J` / `K` | mover panel entre hermanos |
| `>` / `<` | aumentar/disminuir size en 5% |
| `Ctrl+s` | guardar layout |
| `Ctrl+z` | undo, si entra en fase de pulido |

### Modal de panel hoja

- Nombre.
- Comando.
- Args.
- CWD.
- Start suspended.
- Size.
- Focus.
- Borderless.

### Modal de panel contenedor

- Split direction.
- Size.

---

## Zellij Theme Editor

Fase inicial:

- Listar temas embebidos conocidos.
- Mostrar preview.
- Aplicar con `Enter`.
- Actualizar `theme "..."` en `config.kdl`.

Fase posterior:

- Clonar tema a custom.
- Editar slots.
- Guardar bloque `themes { ... }`.

### Decision pendiente: formato de temas

Zellij tiene formato legacy con slots simples (`fg`, `bg`, `red`, etc.) y formato mas nuevo con componentes UI (`text_unselected`, `ribbon_selected`, etc.).

Para v1:

- theme picker no necesita resolver esto;
- basta con cambiar el nombre del tema activo.

Para editor custom:

- decidir explicitamente si se edita formato legacy, formato nuevo, o ambos.

---

## Alacritty Color Editor

Slots principales:

- `[colors.primary]`
  - `background`
  - `foreground`
- `[colors.normal]`
  - `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`
- `[colors.bright]`
  - mismos 8 colores
- `[colors.selection]`
  - `text`
  - `background`
- `[colors.cursor]`
  - `text`
  - `cursor`

Importar tema externo:

1. Reemplazar colores actuales.
2. Agregar `import = [...]` y escribir overrides locales.

Avisos:

- `background` de Alacritty demasiado parecido a `normal.black`.
- `background` de Alacritty demasiado parecido a `bg`/fondo de Zellij.
- seleccion/cursor con contraste bajo.

---

## Preview

El preview debe renderizar dentro del TUI usando estilos propios, no modificando archivos hasta guardar.

Debe incluir:

- mock de prompt;
- mock de `ls --color`;
- mock de diff git;
- barras/pestanas tipo Zellij;
- muestras de seleccion y cursor.

No hace falta ejecutar una instancia real de Zellij en background para preview.

---

## Validaciones

Antes de guardar:

- Validar KDL generado para layouts.
- Validar TOML generado para Alacritty.
- Si `zellij` esta instalado, permitir `zellij setup --check` despues de tocar `config.kdl`.
- Crear backup antes de escribir:
  - `config.kdl.bak.YYYYMMDD-HHMMSS`
  - `alacritty.toml.bak.YYYYMMDD-HHMMSS`
  - `layout.kdl.bak.YYYYMMDD-HHMMSS`

---

## Roadmap

### Fase 0 — Setup del proyecto

- `pyproject.toml`.
- Paquete `src/term_config_tui`.
- Comando `term-config-tui`.
- App Textual minima.
- Tests base.
- Servicios vacios para config, layouts y sesiones.

### Fase 0.5 — Pruebas de I/O reales

- Leer `~/.config/zellij/config.kdl`.
- Cambiar solo `theme "..."` sin reescribir todo el archivo.
- Leer/listar layouts en `~/.config/zellij/layouts`.
- Parsear un layout simple.
- Emitir un layout simple.
- Leer/escribir `alacritty.toml` con `tomlkit`.
- Ejecutar validaciones si `zellij` esta disponible.

Esta fase reduce el riesgo antes de construir mucha UI.

### Fase 1 — Theme Picker Zellij

- Lista de temas embebidos.
- Preview simple.
- Aplicar tema con `Enter`.
- Guardar cambio en `config.kdl`.
- Backup automatico.

Ya es util por si solo.

### Fase 2 — Session Manager Zellij

- Listar sesiones.
- Conectarse a una sesion.
- Crear sesion nueva.
- Crear sesion con layout.
- Cerrar sesion viva.
- Borrar sesion exited.
- Forzar borrado con confirmacion.
- Refrescar estado.

Esta fase resuelve el problema practico de no saber que sesiones estan abiertas ni como cerrarlas.

### Fase 3 — Layout Editor

- Gestor de multiples layouts.
- Editor de tabs.
- Editor de arbol de paneles.
- Modal de panel hoja.
- Modal de panel contenedor.
- Save/load.
- Al guardar, ofrecer abrir/recrear sesion desde Session Manager.

### Fase 4 — Alacritty Color Editor

- Editar slots de color.
- Importar tema.
- Preview.
- Avisos de contraste.
- Guardar con backup.

### Fase 5 — Pulido

- Custom themes Zellij.
- Undo/redo.
- Mejor preview.
- Deteccion mas robusta de versiones de Zellij.
- Acciones rapidas para recrear sesiones.
- Tests con fixtures reales de KDL/TOML.

---

## Estructura del proyecto

```text
~/Documents/term-config-tui/
|-- PLAN.md
|-- pyproject.toml
|-- README.md
|-- src/
|   `-- term_config_tui/
|       |-- __init__.py
|       |-- __main__.py
|       |-- app.py
|       |-- models/
|       |   |-- layout.py
|       |   |-- session.py
|       |   |-- theme.py
|       |   `-- config.py
|       |-- services/
|       |   |-- backups.py
|       |   |-- kdl_io.py
|       |   |-- toml_io.py
|       |   |-- zellij_config.py
|       |   `-- zellij_session.py
|       |-- screens/
|       |   |-- main_menu.py
|       |   |-- session_manager.py
|       |   |-- layout_editor.py
|       |   |-- theme_editor.py
|       |   `-- color_editor.py
|       `-- widgets/
|           |-- pane_tree.py
|           |-- color_picker.py
|           |-- preview.py
|           `-- confirm.py
`-- tests/
    |-- fixtures/
    |   |-- zellij/
    |   `-- alacritty/
    |-- test_zellij_sessions.py
    |-- test_zellij_config.py
    |-- test_layout_io.py
    `-- test_alacritty_toml.py
```

---

## Decisiones abiertas

1. **Formato de temas custom de Zellij**
   - Legacy, nuevo, o ambos.
   - Para el picker inicial no importa.

2. **Como crear sesion con layout segun version de Zellij**
   - Detectar con `zellij --help`.
   - Cubrir al menos la version instalada localmente.

3. **Cuanto preservar en layouts existentes**
   - Opcion simple: layouts creados por la app son totalmente editables; layouts externos se editan parcialmente.
   - Opcion avanzada: round-trip mas fiel de nodos desconocidos.

4. **Recrear sesion automaticamente al guardar**
   - Recomendacion: nunca automatico por defecto.
   - Mostrar accion clara despues de guardar.

---

## Proximos pasos

1. Revisar este plan contra el uso real.
2. Confirmar que el Session Manager entra como fase temprana.
3. Crear proyecto base.
4. Implementar Fase 0 y Fase 0.5 antes de hacer pantallas complejas.
