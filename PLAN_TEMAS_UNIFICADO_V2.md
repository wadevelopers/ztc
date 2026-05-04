# Plan: editor unificado "Temas" (legacy + rich)

## Objetivo

Un editor de tema único que combina los **11 slots legacy** (paleta
ANSI + fg/bg) con **~10 slots ricos** del formato nuevo de Zellij
(seleccion, ribbons, frames). Storage en `config.kdl` user theme
block usando formato mixto (Zellij acepta legacy + rich juntos). Sync
extendido a Alacritty incluyendo `selection.*`.

Resultado: el clone reproduce el built-in fielmente (selection,
ribbons, etc.). Editar un slot afecta ambos lados (Zellij y Alacritty)
sin necesidad de almacenamiento extra ni `THEME_OVERRIDES`/`NON_CLONEABLE_THEMES`.

## Slots expuestos en el editor

### Sección "Paleta ANSI" (legacy, 11 slots)

| Slot | Mapeo Alacritty |
|---|---|
| `fg` | `primary.foreground` |
| `bg` | `primary.background` |
| `black` | `normal.black` |
| `red` | `normal.red` |
| `green` | `normal.green` |
| `yellow` | `normal.yellow` |
| `blue` | `normal.blue` |
| `magenta` | `normal.magenta` |
| `cyan` | `normal.cyan` |
| `white` | `normal.white` |
| `orange` | (solo Zellij) |

### Sección "UI" (rich, arranque MINIMAL — 4 slots)

Empezamos con lo estrictamente necesario para resolver los problemas
concretos identificados:

| Slot | Justificación |
|---|---|
| `text_selected.background` | sync a Alacritty `selection.background` |
| `text_selected.base` | sync a Alacritty `selection.text` |
| `ribbon_selected.background` | tab activo (ej. el #ffdd33 iconico de gruber-darker) |
| `ribbon_selected.base` | texto del tab activo (contrasta con su bg) |

### Slots ricos candidatos a agregar después (según testing)

Si al probar el editor se ve que falta control sobre algún elemento
visible, se agregan de a uno. Lista de candidatos identificados pero
NO incluidos al arranque:

- `ribbon_unselected.{background, base}` — tabs inactivas
- `frame_selected.base` — borde del pane focuseado
- `frame_highlight.base` — highlights de frames
- `exit_code_success.base`, `exit_code_error.base` — output de comandos
- Otros `text_unselected.emphasis_*` si afectan visualmente algo
  notable

Filosofía: el clone preserva los componentes ricos del .kdl tal cual
en `raw_components` (todo, sin filtrar) — pero el editor solo expone
los 4 que arrancamos. Los demás se mantienen opacos en el storage,
no editables, pero Zellij los renderiza igual.

## Cambios en el modelo

### 1. `ZellijTheme.raw_components` (resucitar)

Ya tenemos código previo para esto que revertimos. Hay que rehacerlo:

```python
@dataclass
class ZellijTheme:
    name: str
    source: ThemeSource = "builtin"
    colors: list[ZellijColor] = field(default_factory=list)  # legacy slots
    raw_components: list[Any] = field(default_factory=list)  # kdl.Node de bloques rich
```

### 2. Nuevo modelo para slots ricos editables

Para abstraer el storage (kdl.Node opaco) del editor (que necesita
dict editable):

```python
RICH_SLOTS: list[tuple[str, str]] = [
    ("text_selected", "background"),
    ("text_selected", "base"),
    ("ribbon_selected", "background"),
    ("ribbon_selected", "base"),
    ("ribbon_unselected", "background"),
    ("ribbon_unselected", "base"),
    ("frame_selected", "base"),
    ("frame_highlight", "base"),
    ("exit_code_success", "base"),
    ("exit_code_error", "base"),
]

def read_rich_slot(theme: ZellijTheme, component: str, slot: str) -> str | None:
    """Busca en raw_components el componente y devuelve el slot."""

def write_rich_slot(theme: ZellijTheme, component: str, slot: str, hex_value: str) -> None:
    """Crea o actualiza el slot dentro del componente en raw_components."""
```

## Parser / renderer

### Parser (`list_user_themes`)

Extender para que cuando encuentre un bloque anidado (`text_selected
{ ... }`), lo guarde como `kdl.Node` en `raw_components`. Ya teníamos
ese código en el revert pasado, hay que rehacerlo.

### Renderer (`render_themes_block`)

```kdl
themes {
    my-theme {
        fg "#..."
        bg "#..."
        ...
        text_selected {
            base "#..."
            background "#..."
        }
        ribbon_selected {
            background "#..."
            base "#..."
        }
        ...
    }
}
```

Mismo formato que ya soportamos antes. Re-emite los rich components
serializando los `kdl.Node`. Normalizar floats sueltos (`1.0` -> `1`)
ya lo teníamos.

## Cambios en clone

Cuando se clona un built-in:

1. Slots legacy: derivados del `.kdl` como hoy + `THEME_OVERRIDES` (si
   sobreviven — ver más abajo).
2. Slots ricos: copiar directamente los componentes del `.kdl` bundled
   limitado a los que están en `RICH_SLOTS` (no todos los ~60).
3. Si el theme activo coincide con `src` y hay `alacritty_path`:
   overlay desde alacritty afectando legacy AND `text_selected.*`
   (extraído desde `selection.*` de alacritty).

## Cambios en theme_sync

Extender `_LEGACY_TO_ALACRITTY` con un dict paralelo
`_RICH_TO_ALACRITTY`:

```python
_RICH_TO_ALACRITTY: list[tuple[str, str, str, str]] = [
    # (rich_component, rich_slot, alacritty_group, alacritty_slot)
    ("text_selected", "background", "selection", "background"),
    ("text_selected", "base", "selection", "text"),
]
```

`sync_alacritty_with_zellij_theme` hace ambas pasadas.

`_resolve_zellij_slots` devuelve dos diccionarios: legacy + rich.

## Cambios en el editor

`CustomThemeEditorScreen` (renombrar a `ThemeEditorScreen` quizá)
muestra dos secciones:

```
+---------------------------+--------------------------+
| Theme: my-mocha           |                          |
| Tipo: user-defined        |                          |
|                           |                          |
| -- Paleta ANSI --         | name: text_selected.bg  |
| > fg          #cdd6f4 ▇▇  | value: #585b70           |
|   bg          #1e1e2e ▇▇  | (preview swatch grande)  |
|   black       #1e1e2e ▇▇  |                          |
|   red         #f38ba8 ▇▇  |                          |
|   ...                     |                          |
|                           |                          |
| -- UI (Zellij) --         |                          |
|   text_selected.bg #5856 ▇|                          |
|   ribbon_selected.bg #a6e |                          |
|   ...                     |                          |
+---------------------------+--------------------------+
```

Bindings idénticos a hoy: `Enter` editar slot, `s` save, `x` reset
(elimina slot del config.kdl), Esc volver con confirm si dirty.

## Eliminaciones

- `NON_CLONEABLE_THEMES` — gruber-darker pasa a clonarse normalmente
  (sus rasgos únicos se preservan en `ribbon_selected.background` etc).
- `THEME_OVERRIDES` — la mayoría se vuelve innecesaria porque el clone
  preserva todo lo importante. Reviso uno por uno:
  - `ayu-light white = #5c6166` — sigue siendo necesario porque el
    .kdl de ayu-light pone blanco (`#fcfcfc`) en `text_unselected.base`
    que es de donde derivamos `white`. Override sigue.
  - `catppuccin-latte red = #ea76cb` — esta era una decision
    estética que dependía de qué color asignamos a "red" del clon.
    Con clone que preserva los rich components y la conversión de
    Zellij, podríamos no necesitarla. Verificar con tests.

## Plan de fases

### Fase 1: backend (sin tocar UI)

- **Commit 1.1**: resucitar `raw_components` en model + parser + renderer.
  Tests del round-trip parser → renderer.
- **Commit 1.2**: clone preserva rich components (subset de
  `RICH_SLOTS`). Tests del clone.
- **Commit 1.3**: `_RICH_TO_ALACRITTY` y sync extendido. Tests del sync
  para `selection.*`.
- **Commit 1.4**: helpers `read_rich_slot` / `write_rich_slot` para el
  modelo. Tests unitarios.

### Fase 2: editor

- **Commit 2.1**: `ThemeEditorScreen` muestra ambas secciones legacy +
  rich. Edición funciona para ambos. Tests del screen.
- **Commit 2.2**: refresh live al guardar afecta TUI (ya lo teníamos
  para legacy, extender a rich).

### Fase 3: limpieza

- **Commit 3.1**: eliminar `NON_CLONEABLE_THEMES`. Tests adaptados.
- **Commit 3.2**: revisar `THEME_OVERRIDES` — eliminar los que ya no
  hagan falta. Mantener solo los que sigan siendo correctivos.
- **Commit 3.3**: actualizar NOTES.md.

## Open questions

1. **¿`bright.*` de Alacritty queda fuera del editor unificado?** Mi
   propuesta: sí. El usuario puede editarlos en el Color Editor cuando
   quiera. Default razonable: derivar como versión más clara de
   `normal.*`.

2. **¿El Color Editor sobrevive como módulo aparte para
   `bright.*`/`cursor.*` y para importar `.toml`?** Mi propuesta: sí,
   pero quizás renombrarlo "Colores Alacritty (avanzado)".

3. **¿Hay rich slots que NO están en mi subset de 10 que quieras
   exponer?** Por ejemplo `text_unselected.emphasis_*` (los acentos
   "extras"). Si los exponemos, el editor crece. Si no, se preservan
   opacos en `raw_components` pero no editables.

4. **¿El editor edita el slot directamente y guarda inmediato, o
   acumula cambios y `s` los persiste?** Hoy es lo segundo
   (acumula + save). Mantener.

## Trade-offs

A favor:
- Storage limpio (un solo archivo: `config.kdl`).
- No hace falta `themes.toml` ni `THEME_OVERRIDES` masivos.
- Clone reproduce built-in fielmente.
- `NON_CLONEABLE_THEMES` se elimina (gruber-darker se clona OK).
- `selection.*` del clone funciona.
- Combina los dos módulos (Temas Zellij + Colores Alacritty) en uno
  para los slots compartidos.

En contra:
- Más slots editables (~21 vs 11) — el editor es más largo.
- Resucitar código que revertimos antes (parser/renderer mixto).
- Risk de que algún rich slot raro de algún tema cause issues al
  re-emitirse. Mitigación: tests por tema.

## Estimación

Aproximadamente:
- Fase 1 (backend): 1 sesión.
- Fase 2 (editor): 1 sesión.
- Fase 3 (limpieza): media sesión.

Total: ~2.5 sesiones de trabajo concentrado.

## Resumen ejecutivo

Refactor del editor de themes para combinar legacy (ANSI) + rich
(UI) en una sola pantalla, storage mixto en `config.kdl`, sync
extendido a Alacritty `selection.*`. Soluciona:

- Selection invisible en clones.
- gruber-darker no clonable (deja de ser excepción).
- Necesidad de `THEME_OVERRIDES` masivos.
- Duplicación entre módulo de Zellij y de Alacritty.

3 fases incrementales, cada commit pasa tests.

Listo para empezar Fase 1 cuando confirmes las open questions.
