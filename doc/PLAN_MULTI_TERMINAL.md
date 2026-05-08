# Plan: soporte multi-terminal + detección en runtime

Estado: **ejecutado** (Fases A → C + E). v6 documenta el estado final
implementado. Ghostty (Fase D) queda diferida a un plan posterior.

## Historia de revisiones

- **v1** — versión inicial: 4 fases (detección → abstracción → kitty+ghostty → docs).
- **v2** — incorpora review externo: gating de menú por backend
  disponible, detección en `__init__`, interfaz `TerminalBackend`
  completa, firma de `compute_warnings` desacoplada, acoplamientos a
  Alacritty antes omitidos (`zellij_themes.clone_theme`,
  `widgets/confirm.py`, `_LEGACY_TO_ALACRITTY`).
- **v3** — verificación de sintaxis kitty/ghostty contra docs
  oficiales. Hex shorthand y normalization. *(Contenía afirmaciones
  incorrectas sobre ghostty corregidas en v4.)*
- **v4** — segundo pase de review. Cambios estructurales:
  - **Ghostty diferido a Fase D futura** (fuera del scope inicial).
    Razón: `config-file` directives se procesan al final del archivo
    actual y los archivos incluidos ganan sobre el huésped; nuestra
    estrategia "append-at-end" de v3 no funcionaba. Verificado contra
    `https://ghostty.org/docs/config`.
  - **Reordenamiento de fases** A→B→C→D: ahora el desacoplamiento
    viene primero (era Fase 2) y la detección+UI va después (era
    Fase 1). Razón: evita un "registry stub" transitorio que existía
    solo para gatear el menú antes de tener la abstracción.
  - **Env var override `TERM_CONFIG_TUI_BACKEND`** agregado a la
    detección. Útil para tests, edge cases y multiplexores raros.
    Default `auto`.
  - Correcciones a las afirmaciones falsas sobre ghostty en v3.
- **v5** — tercer pase de review. Fixes puntuales:
  - **Fase B test de Kitty** corregido: en Fase B el registry solo
    tiene Alacritty, así que el test debe esperar `(no soportada)`.
    El caso "kitty habilita el editor" pasa a Fase C.
  - **Inyección de backend en el constructor de la app** definida
    explícitamente: `TermConfigApp(paths, backend, backend_path)`
    para que los tests no toquen `~/.config/`.
  - **Override inválido** (valor distinto de `auto`/`alacritty`/`kitty`)
    define comportamiento explícito: `kind=unsupported` + toast.
  - **UX rule** desacoplada: colores y Zellij son bloques
    independientes; cada uno se habilita por sus propias condiciones.
  - **Aclaración Fase A**: `app.backend` se setea con Alacritty
    hardcodeado en Fase A; en Fase B sale de detección.
- **v6** — post-ejecución. Ajuste durante Fase C (desvío aprobado):
  - **Includes en kitty pasan de "limitación documentada" a feature
    real.** Razón: caso real verificado en producción —
    `~/.config/kitty/kitty.conf` típico tiene solo
    `include themes/<x>.conf` y los colores viven en el include; sin
    expandir, el editor mostraba "(sin definir)" en todo y era
    inutilizable. Se implementó expansión recursiva (`include`, no
    `globinclude`) con depth limit 5. Lectura linealiza main+includes
    en orden de procesamiento de kitty; escritura toca solo el
    archivo principal y aprovecha last-wins para que las ediciones
    persistan aunque el usuario cambie el include de tema.
  - **Riesgo "kitty `include` no se gana siempre" eliminado**: con
    la expansión + escritura always-at-end-of-main, garantizamos
    que la línea editada gana sobre cualquier include.

## Objetivo

Que la app deje de estar atada a Alacritty y pueda editar colores
también de **Kitty**, eligiendo el backend automáticamente según en
qué terminal corre el TUI. Si la terminal en la que se ejecuta no
está soportada, "Colores de terminal" se deshabilita y se avisa. Las
funciones de Zellij siguen disponibles mientras Zellij esté
instalado. **Ghostty queda fuera de este plan** y se aborda después
en su propio plan (ver Fase D).

## Análisis del codebase actual

Acoplamiento a Alacritty (todo lo que toca el nombre):

| Archivo | Qué hace | Acoplamiento |
|---|---|---|
| `services/alacritty.py` (270 LoC) | I/O TOML: `read_slot`, `write_slot`, `delete_slot`, `import_theme_file`, `compute_warnings`, helpers hex/contraste | Mezcla: I/O específico de TOML + utilidades genéricas (hex, WCAG) |
| `services/theme_sync.py` (162 LoC) | Mapping Zellij → slots Alacritty + escritura. Define `_LEGACY_TO_ALACRITTY` (importado también desde `zellij_themes.py:465`) | Backend hardcodeado |
| `services/zellij_themes.py:407,444-474` | `clone_theme()` recibe `alacritty_path` opcional; `_read_alacritty_legacy_slots()` usa `ala_svc.read_slot/is_valid_hex/normalize_hex` para overlay del tema activo | Lectura directa de Alacritty |
| `models/config.py` | `Paths.alacritty_config: Path` | 1 campo |
| `app.py:131-137` | Menú "Colores Alacritty" → `AlacrittyColorEditorScreen(alacritty_path=...)` | Menú + label + push_screen |
| `screens/color_editor.py` | Usa `alacritty.KNOWN_SLOTS`, `read_slot`, `write_slot`, `compute_warnings`, etc. | Importa el módulo crudo |
| `screens/theme_editor.py:248-256, 380-388` | `theme_sync.sync_alacritty_with_zellij_theme(alacritty_path=...)` | 2 call sites |
| `screens/custom_theme_editor.py:316-323` | Idem | 1 call site |
| `widgets/confirm.py:484, 500` | `from ztc.services.alacritty import is_valid_hex, normalize_hex` | 2 imports |
| Tests | `test_alacritty_service.py`, `test_alacritty_toml.py`, `test_theme_sync.py`, `test_smoke.py`, `test_theme_picker_screen.py`, `test_custom_theme_editor_screen.py` (estos 3 últimos usan `Paths.alacritty_config` en fixtures) | Cobertura buena |

Insight clave: Alacritty y Kitty comparten el mismo **vocabulario de
20 slots** (primary fg/bg + 8 normal + 8 bright + selection text/bg +
cursor text/cursor). Las diferencias son: formato del archivo
(TOML vs flat key-value), nombres de las keys, formato del valor
(hex `#rrggbb` con tolerancia a `#rgb` shorthand en kitty).

Lo que ya está bien:

- Slots y mapping Zellij→Alacritty están en dicts planos, fáciles de
  generalizar.
- `Paths` es un solo dataclass → fácil de extender.
- Tests cubren el I/O de Alacritty → buena base para regresión.

## UX objetivo

Detección al arranque:

- **Override por env var**: `TERM_CONFIG_TUI_BACKEND` puede valer
  `auto` (default) o uno de `alacritty`, `kitty` (en futuro
  `ghostty`). Si está seteado a un valor distinto de `auto`, la
  detección automática se saltea y se usa el backend indicado.
  Útil para tests, multiplexores raros, shells con env vars
  filtradas, troubleshooting.

- **Detección automática (cuando `TERM_CONFIG_TUI_BACKEND=auto`)**:
  env vars distintivas que sobreviven multiplexores:

  | Terminal | Variable distintiva |
  |---|---|
  | Alacritty | `ALACRITTY_WINDOW_ID` o `ALACRITTY_SOCKET` |
  | Kitty | `KITTY_PID` o `KITTY_WINDOW_ID` |
  | otras / nada | unsupported |

- Fallback secundario: `TERM_PROGRAM`, `TERM`.
- Zellij: `shutil.which("zellij")` (instalado).
- SSH: `SSH_CONNECTION` presente.

Reglas de UI al arranque (**colores y Zellij son independientes**:
cada bloque se evalúa por separado):

**Bloque "Colores de terminal":**

- Habilitado iff `is_backend_available(detected.kind) and not via_ssh`.
- Si terminal **no soportada** o no detectada → toast:
  `Terminal no soportada para edición de colores.
  Soportadas: Alacritty, Kitty.`
  Opción visible con sufijo `(no soportada)`.
- Si SSH detectado → opción deshabilitada con sufijo `(SSH)` y
  mensaje: `Estás por SSH; la edición de colores no aplica al cliente.`
- Si override por env var es inválido → opción deshabilitada con
  toast de override inválido (ver tabla del detector).

**Bloque "Zellij" (temas + layouts):**

- Habilitado iff `zellij_installed`.
- Si Zellij no instalado → toast + ambas opciones de Zellij
  deshabilitadas. **No afecta a "Colores de terminal".**

**Caso happy-path** (todo verde, sin avisos): terminal soportada con
backend disponible + no SSH + Zellij instalado.

Sin override manual via UI, sin pantalla de Ajustes, sin
cross-terminal config. El override por env var es el único escape
hatch y es invisible por defecto.

## Plan por fases

### Fase A — Abstracción de backend de terminal

Refactor sin features nuevas: existe una interfaz `TerminalBackend` y
Alacritty es uno de sus implementadores. Al terminar Fase A, todo
sigue funcionando como hoy (solo Alacritty se usa) pero la
arquitectura ya soporta backends nuevos.

Cambios:

- Extraer utilidades genéricas de `services/alacritty.py` a
  `services/colors.py`: `is_valid_hex`, `normalize_hex`,
  `_hex_to_rgb`, `_rel_luminance`, `contrast_ratio`, `Warning`,
  `compute_warnings`.
- **Cambio de firma de `compute_warnings`**: ya no recibe `doc`
  (acoplado al formato), sino un dict de slots:

  ```python
  def compute_warnings(
      slots: dict[CanonicalSlot, str],
      *,
      zellij_bg: str | None = None,
  ) -> list[Warning]: ...
  ```

  Cada caller arma el dict iterando `backend.read_slot(...)` por los
  slots que le interesan (bg, fg, black, sel_bg, cursor).

- Nuevo `services/terminals/__init__.py` con la interfaz definitiva:

  ```python
  CanonicalSlot = tuple[str, str]            # (group, name)
  BackendDoc = Any                           # opaco; cada backend lo tipa internamente

  class TerminalBackend(Protocol):
      kind: str                              # "alacritty" | "kitty"
      display_name: str
      def default_config_path(self) -> Path: ...
      def load(self, path: Path) -> BackendDoc: ...
      def save(self, doc: BackendDoc, path: Path) -> Path | None: ...
      # Path | None: None cuando no había archivo previo (no hay backup que crear).
      def read_slot(self, doc: BackendDoc, slot: CanonicalSlot) -> str | None: ...
      def write_slot(self, doc: BackendDoc, slot: CanonicalSlot, value: str) -> None: ...
      def delete_slot(self, doc: BackendDoc, slot: CanonicalSlot) -> bool: ...
      def supported_slots(self) -> list[CanonicalSlot]: ...
  ```

  - **`import_theme_file` no entra en la Protocol.** Es una capability
    específica del editor de Alacritty (importar de otro
    `alacritty.toml`). Queda como método público de
    `AlacrittyBackend` (no de la Protocol). El editor lo invoca con
    `isinstance(backend, AlacrittyBackend)` o un Protocol secundario
    `SupportsImport` que solo Alacritty implementa.
- Mover `services/alacritty.py` → `services/terminals/alacritty.py`,
  adaptar a la interfaz (clase `AlacrittyBackend` que envuelve la
  lógica TOML existente). **Sin shim** en la ubicación vieja: todos
  los imports se migran en el mismo commit (ver "Alias encubiertos
  prohibidos" en `.claude/rules/agent-behavior.md`).
- Nuevo `services/terminals/registry.py` con:
  - `get_backend(kind: str) -> TerminalBackend | None`
  - `is_backend_available(kind: str) -> bool`
  - `available_kinds() -> list[str]`
- Refactor `services/theme_sync.py`: recibe
  `backend: TerminalBackend` + path en vez de `alacritty_path`. El
  mapping Zellij→canonical-slot queda igual. **`_LEGACY_TO_ALACRITTY`
  se renombra a `_LEGACY_TO_CANONICAL`** (apunta a slots canónicos
  `(group, name)`, no a Alacritty específicamente). El backend
  traduce de canonical a su nomenclatura propia internamente.
- Refactor `services/zellij_themes.py`: `clone_theme()` y
  `_read_alacritty_legacy_slots` se generalizan. Reciben
  `backend: TerminalBackend | None` + `path: Path | None` en lugar de
  `alacritty_path`. La lógica de overlay sigue igual pero lee vía la
  interfaz.
- Refactor `widgets/confirm.py:484, 500`: imports cambian de
  `from ztc.services.alacritty import ...` a
  `from ztc.services.colors import ...`.
- Refactor `screens/color_editor.py`: recibe `backend` + `path`.
  Renombrar a `ColorEditorScreen`. Toda llamada
  `alacritty.read_slot(...)` → `self.backend.read_slot(...)`.
  `compute_warnings` se invoca con el dict de slots construido en el
  screen.
- Refactor `screens/theme_editor.py` y `custom_theme_editor.py`:
  `getattr(self.app.paths, "alacritty_config", ...)` → leer
  `self.app.backend` + `self.app.backend_path` (atributos nuevos en
  la app). En Fase A se setean en `__init__` con
  `AlacrittyBackend()` hardcodeado y su `default_config_path()`. En
  Fase B salen del resultado de la detección.
- Refactor `models/config.py:Paths`: eliminar `alacritty_config`. La
  ruta sale del backend (`backend.default_config_path()`); `Paths`
  queda solo con cosas de Zellij.
- En esta fase, la app sigue forzando backend Alacritty
  hardcodeado en `app.__init__` (no hay detección todavía). Solo el
  refactor estructural.
- **Constructor de la app** se amplía para permitir inyección en
  tests sin tocar `~/.config/`:

  ```python
  class TermConfigApp(App[None]):
      def __init__(
          self,
          paths: Paths | None = None,
          backend: TerminalBackend | None = None,
          backend_path: Path | None = None,
      ) -> None: ...
  ```

  Producción: `backend=None` → la app instancia `AlacrittyBackend()`
  y `backend_path = backend.default_config_path()`. Tests: inyectan
  `backend=AlacrittyBackend()` + `backend_path=tmp_path/"alacritty.toml"`
  (o un `FakeBackend`).
- Tests:
  - Renombrar `test_alacritty_service.py` →
    `test_terminal_alacritty.py`, ajustar imports.
  - `test_alacritty_toml.py`, `test_theme_sync.py`: actualizar para
    pasar el backend.
  - `test_smoke.py`, `test_theme_picker_screen.py`,
    `test_custom_theme_editor_screen.py`: actualizar fixtures que
    usaban `Paths.alacritty_config`. Ahora la app inyecta el backend.
  - `test_zellij_themes_crud.py` (cubre `clone_theme`): actualizar
    para pasar backend.
  - Nuevo: tests de la interfaz `TerminalBackend` con un
    `FakeBackend` minimal para verificar que el editor funciona
    contra cualquier implementación.

Tamaño: refactor de ~600 LoC. Riesgo de regresión moderado, los tests
existentes lo cubren.

### Fase B — Detección runtime + UI

La app sabe en qué terminal corre y la UX queda lista. Se conecta el
registry de Fase A a la detección.

Cambios:

- Nuevo `services/runtime_detect.py`:
  - `detect_terminal() -> TerminalDetection` (dataclass:
    `kind: Literal["alacritty","kitty","unsupported"]`,
    `via_ssh: bool`,
    `raw_marker: str | None` para debug).
  - **Primer paso del detector**: chequear
    `os.environ.get("TERM_CONFIG_TUI_BACKEND")` con esta tabla:

    | Valor | Comportamiento |
    |---|---|
    | `None`, `""`, `"auto"` | Autodetect (sigue el resto del flujo) |
    | `"alacritty"` o `"kitty"` | Retorna ese kind directo, saltea autodetect |
    | Cualquier otro valor (ej. `"wezterm"`, `"potato"`) | `kind=unsupported`, `raw_marker="override:<valor>"`. El boot dispara un toast de override inválido (`Valor inválido para TERM_CONFIG_TUI_BACKEND: '<valor>'. Valores válidos: auto, alacritty, kitty.`) y la app cae a comportamiento de terminal no soportada. |
  - Resto: env vars de la tabla de UX, fallback a `TERM_PROGRAM` /
    `TERM`.
  - `detect_zellij_installed() -> bool`.
- Edit `app.py`:
  - **`__init__`** (no `on_mount`): corre detección y guarda
    `self.detected_terminal` + `self.zellij_installed` +
    `self.backend` + `self.backend_path`. Razón: el ciclo de Textual
    es `__init__` → `compose` → `on_mount`, y `compose` necesita los
    datos para renderizar el menú con el estado correcto.
  - `compose`: las opciones del menú aplican `disabled=True` y
    sufijo `(no soportada)` / `(zellij no instalado)` / `(SSH)`
    según el caso. Renombrar "Colores Alacritty" → "Colores de
    terminal". Habilita "Colores de terminal" **solo si**
    `is_backend_available(self.detected_terminal.kind) and not via_ssh`.
  - `on_mount`: dispara las notificaciones por cada caso detectado
    (toast es UI-side, va después de mount).
- Edit `_on_menu_selected`: guard defensivo si la opción está
  disabled.
- Tests:
  - Unitarios de `detect_terminal()` con env mockeada: cada terminal
    soportada, SSH, override env var, ninguno (unsupported).
  - Tests de `app.py` con `App.run_test()`:
    - Env Alacritty mockeada → opción habilitada y abre editor
      Alacritty.
    - Env Kitty mockeada → opción **deshabilitada** con `(no
      soportada)` (en Fase B el registry solo tiene Alacritty; el
      caso "Kitty habilita el editor" se testea en Fase C).
    - Env desconocida → opción deshabilitada con `(no soportada)`.
    - SSH detectado → opción deshabilitada con `(SSH)`.
    - `TERM_CONFIG_TUI_BACKEND=alacritty` con env de Kitty real →
      override gana, abre Alacritty editor.
    - `TERM_CONFIG_TUI_BACKEND=potato` (valor inválido) →
      `kind=unsupported`, toast de override inválido, opción
      deshabilitada.

Tamaño: ~180 LoC + ~150 LoC tests.

> Nota: Fase B asume que Fase C **no** está hecha todavía. En ese
> estado, el registry tiene solo Alacritty. Si el usuario corre desde
> Kitty, la opción aparece deshabilitada como `(no soportada)` —
> exactamente como cuando corre desde gnome-terminal. Es UX
> consistente y no rompe nada. Cuando Fase C aterrice, esa misma
> detección habilitará el editor sin tocar Fase B.

### Fase C — Backend Kitty

Cambios:

- Nuevo `services/terminals/kitty.py`:
  - **Sintaxis** (verificado contra https://sw.kovidgoyal.net/kitty/conf):
    - `key value` separado por espacio (no `=`).
    - Comentarios `#` al inicio de línea.
    - Hex aceptado: `#rrggbb` y `#rgb` (shorthand).
    - Sin secciones; flat key-value.
  - Mapping canónico → kitty:
    - `("primary","background")` ↔ `background`
    - `("primary","foreground")` ↔ `foreground`
    - `("normal","black")` … `("normal","white")` ↔ `color0` … `color7`
    - `("bright","black")` … `("bright","white")` ↔ `color8` … `color15`
    - `("selection","text")` ↔ `selection_foreground`
    - `("selection","background")` ↔ `selection_background`
    - `("cursor","cursor")` ↔ `cursor`
    - `("cursor","text")` ↔ `cursor_text_color`
  - I/O: leer todas las líneas, regex `^(\S+)\s+(.*)$` para parsear,
    preservar líneas no-color al guardar.
  - **Duplicados**: si un slot aparece más de una vez, gana la última
    ocurrencia (semántica de kitty). `read_slot` devuelve la última.
  - **Escritura de slot ausente**: append al final del archivo.
  - **Valores especiales / no-hex** (verificados, parsing
    defensivo, NO scope creep — solo preservación):
    - `none` (cursor, selection_foreground, selection_background) →
      reverse video.
    - `background` (cursor) → matchea cell background.
    - Named colors (`black`, `red`, etc.).
    - Formatos avanzados: `oklch(...)`, `cielab(...)`.
    - Estos se preservan tal cual al leer; `read_slot` devuelve el
      valor textual. El editor los muestra con swatch vacío y los
      marca como "valor especial / formato no-hex" (editable solo
      si el usuario decide reemplazar por hex). El objetivo es **no
      romper la config del usuario** ante formatos legítimos que la
      app no soporta para edición visual.
  - **Includes** (semántica v6, implementada):
    - **Lectura**: `include otro.conf` se expande recursivamente con
      depth limit 5. Path relativo se resuelve contra el archivo
      padre. Includes faltantes se ignoran silenciosamente.
      `globinclude` y `envinclude` NO se expanden — solo `include`.
      `read_slot` linealiza main+includes en orden de procesamiento
      de kitty y devuelve la última coincidencia (last-wins).
    - **Escritura**: solo el archivo principal
      (`default_config_path()`) se modifica. Si la entrada ganadora
      viene del main, se actualiza in-place; si viene de un include
      o no existe, se appendea al final del main para que kitty la
      procese al final y gane vía last-wins. Caso sutil: main tiene
      la key ANTES de un include que también la tiene → write
      detecta que el include estaba ganando y appendea al final, no
      toca la línea del main que era invisible al usuario.
    - **Borrado**: solo del archivo principal. Si el slot también
      venía de un include, después del delete vuelve a ganar el
      del include. Si el slot solo existe en un include, delete
      devuelve `False` (no tocamos archivos del usuario).
  - Default path (verificado): `$KITTY_CONFIG_DIRECTORY/kitty.conf`
    si está seteado, else `$XDG_CONFIG_HOME/kitty/kitty.conf` si
    está seteado, else `~/.config/kitty/kitty.conf`.
- Update registry para registrar `KittyBackend`.
- Tests con fixtures realistas:
  - `tests/fixtures/kitty/kitty.conf` con casos comunes.
  - **Round-trip**: read → write → read preserva el archivo
    byte-a-byte excepto las líneas que el test modifica.
  - **Duplicados**: archivo con `color0 #xxx` duplicado → leer
    devuelve la última, escribir actualiza la última.
  - **Slots ausentes**: archivo sin `cursor` → escribir lo agrega
    al final.
  - **Hex shorthand**: archivo con `color1 #f00` → leer devuelve
    `#ff0000` (expandido a 6 dígitos).
  - **Valores especiales**: archivo con `selection_foreground none`
    → leer devuelve `"none"`, no rompe.
  - **Includes**: cubrir simple, path relativo, path absoluto,
    nested, missing file (silent), main override include (segun
    orden), include override main, circular (depth limit), write
    cuando solo en include (append), write cuando ya en main (update
    in-place), write cuando include posterior overrides main (append),
    delete remueve solo del main, delete-only-in-include returns
    False.

Tamaño: ~250 LoC + ~200 LoC tests.

### Fase D — Backend Ghostty (futura, fuera de scope inicial)

**No se implementa en este plan.** Se deja como referencia para un
plan posterior. Razones para diferir:

1. **`config-file` directives ganan sobre el huésped**: verificado
   contra https://ghostty.org/docs/config — *"`config-file` keys are
   processed at the end of the current file, meaning keys in the
   loaded file will not be overridden by keys appearing later in the
   current file."* Nuestra estrategia line-based de "append-at-end"
   no garantiza precedencia. Para implementar bien, hay que decidir
   una política específica (ej. la app crea/edita un archivo
   propio y le pide al usuario un `config-file = path/to/our.conf` al
   final, que carga último y gana).
2. **Naming `config` vs `config.ghostty`**: los docs hablan del
   archivo como uno solo (alternativos), no como layered. Hay que
   verificar bien la semántica antes de implementar (dato no
   100% claro hoy).
3. **Palette format**: 16 ANSI bajo una key repetida con subkey
   (`palette = N=#xxx`) requiere parser distinto al resto.

Cuando se haga, los pasos son análogos a Fase C (backend nuevo en
`services/terminals/ghostty.py`, registrar en registry, tests
round-trip), más la decisión de política para `config-file`.

### Fase E — Pulido + docs

- Tests E2E:
  - Env mockeada de Kitty → menú abre el editor con backend Kitty →
    edita un slot → guarda → archivo refleja el cambio.
- Update `README.md` con la lista de terminales soportadas, la
  política de detección automática, el override por env var
  (`TERM_CONFIG_TUI_BACKEND`), y la limitación documentada de los
  `include` directives en kitty.
- Update `PLAN.md` reflejando la arquitectura nueva.

## Decisiones cerradas

1. **Vocabulario canónico = el actual de Alacritty**
   (`primary/normal/bright/selection/cursor`, 20 slots). Todos los
   backends traducen hacia/desde eso. Razón: ya está testeado y kitty
   cabe sin fricción.
2. **`compute_warnings` es genérico** (vive en `colors.py`, recibe
   dict de slots). Las heurísticas WCAG no son terminal-específicas.
3. **`import_theme_file` queda fuera de la Protocol**, como
   capability solo de `AlacrittyBackend`. El editor lo expone
   condicionalmente.
4. **Backups** los maneja cada backend en `save()` con la misma
   convención `<archivo>.bak.<timestamp>` que ya tiene `toml_io`.
   `save()` retorna `Path | None` (None cuando no había archivo
   previo).
5. **Preservación de formato en kitty:** estrategia line-based con
   regex; preservar comentarios, orden, includes; tocar solo las
   líneas afectadas; append al final para slots nuevos.
6. **Duplicados y valores no-hex en kitty**: respetar la semántica
   del archivo (last-occurrence-wins, valores especiales preservados
   como texto), no fallar.
7. **Hex normalization**: al leer, `#rgb` se expande a `#rrggbb`. Al
   escribir, siempre `#rrggbb` lowercase.
8. **Eliminar `Paths.alacritty_config`**: la detección + el backend
   mandan, sin overrides ocultos en config files. El override
   válido es la env var `TERM_CONFIG_TUI_BACKEND`.
9. **Override por env var `TERM_CONFIG_TUI_BACKEND`**: valores
   `auto` (default), `alacritty`, `kitty`. Solo afecta la
   detección; no abre UI ni pantalla de Ajustes.
10. **Sin shim de compat en `services/alacritty.py`** después de
    moverlo: todos los imports se migran en el mismo commit. La
    regla "Alias encubiertos prohibidos" del proyecto desautoriza
    el atajo.
11. **Ghostty diferido**: por las complicaciones de `config-file`
    semantics, va a un plan posterior.

## Riesgos

- **Format roundtrip kitty:** el parser line-based puede fallar ante
  construcciones poco comunes (multiline values, continuation
  backslash, etc.). Mitigación: tests con fixtures realistas + fallar
  fuerte solo ante líneas que no matcheen ningún patrón conocido (no
  ante valores raros dentro de una línea válida).
- ~~**Kitty `include` no se gana siempre**~~: resuelto en v6 con la
  expansión + escritura always-at-end-of-main. La precedencia sobre
  includes está garantizada porque la línea editada queda al final
  del archivo principal y kitty aplica last-wins.
- **Detección ambigua bajo Zellij:** los markers de Alacritty/Kitty
  se preservan como env vars al spawnear el shell, así que Zellij
  no debería romper nada. Verificar con tests de integración manual.
- **Refactor de Fase A toca screens y tests de screens:** la lista
  está enumerada arriba (`test_smoke`, `test_theme_picker_screen`,
  `test_custom_theme_editor_screen`, `test_zellij_themes_crud`).
  Mantener cobertura ≥ actual.
