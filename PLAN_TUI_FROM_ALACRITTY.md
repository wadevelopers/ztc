# Plan: TUI deriva sus colores desde Alacritty (no desde Zellij)

## Objetivo

Que el Textual theme del TUI se construya 100% desde `alacritty.toml`,
no desde el tema activo de Zellij. Asi:

- El TUI siempre matchea visualmente la terminal donde corre.
- Editar un slot en Colores Alacritty cambia el TUI al instante.
- Aplicar un tema Zellij cambia el TUI al instante (porque el sync
  Zellij→Alacritty escribe nuevos colores y el TUI los lee).
- El TUI deja de tener una decision artistica copiada de cada tema
  Zellij — usa siempre el mapping ANSI estandar.

## Mapping de derivacion

| Token Textual | Origen Alacritty | Fallback si falta |
|---|---|---|
| `background` | `primary.background` | `#1e1e1e` |
| `foreground` | `primary.foreground` | `#cdd6f4` |
| `surface` | `primary.background` | igual a `background` |
| `panel` | `bright.black` | `normal.black` o `#3a3a3a` |
| `primary` | `normal.blue` | `foreground` |
| `secondary` | `normal.magenta` | `foreground` |
| `accent` | `normal.cyan` | `foreground` |
| `success` | `normal.green` | `#50fa7b` |
| `warning` | `normal.yellow` | `#f1fa8c` |
| `error` | `normal.red` | `#ff5555` |
| `dark` | `luminance(primary.background) < 0.5` | `True` |

## Cambios concretos

### 1. Nueva funcion `build_textual_theme_from_alacritty`

En `services/zellij_theme_assets.py` (o en un modulo nuevo
`services/textual_theme.py`):

```python
def build_textual_theme_from_alacritty(
    doc: TOMLDocument, name: str = "current"
) -> TextualTheme | None:
    """Construye un Textual Theme leyendo slots de alacritty.toml."""
    primary_bg = read_slot(doc, "primary", "background")
    primary_fg = read_slot(doc, "primary", "foreground")
    if not primary_bg or not primary_fg:
        return None
    return Theme(
        name=name,
        background=primary_bg,
        foreground=primary_fg,
        surface=primary_bg,
        panel=read_slot(doc, "bright", "black") or "#3a3a3a",
        primary=read_slot(doc, "normal", "blue") or primary_fg,
        secondary=read_slot(doc, "normal", "magenta") or primary_fg,
        accent=read_slot(doc, "normal", "cyan") or primary_fg,
        success=read_slot(doc, "normal", "green") or "#50fa7b",
        warning=read_slot(doc, "normal", "yellow") or "#f1fa8c",
        error=read_slot(doc, "normal", "red") or "#ff5555",
        dark=is_dark(primary_bg),
    )
```

### 2. Modificar `App.register_zellij_themes`

Hoy registra UN Textual theme por cada tema Zellij (built-in + user)
con el mismo nombre que el Zellij. Despues `apply_theme_for_zellij`
hace `self.theme = nombre_zellij`.

Cambio: registrar UN solo Textual theme llamado "current" (o similar)
construido desde Alacritty. Cada vez que cambia algo (apply tema
Zellij, save Color Editor, save Custom Theme Editor activo), se
re-registra ese mismo "current" con los nuevos colores.

```python
def register_zellij_themes(self) -> None:
    doc = toml_io.load_toml(self.paths.alacritty_config)
    theme = zta.build_textual_theme_from_alacritty(doc, name="current")
    if theme is not None:
        self.register_theme(theme)
```

### 3. Modificar `apply_theme_for_zellij`

Ya no aplica el theme con el mismo nombre que Zellij. Aplica "current"
y fuerza el re-watch para tomar los hex actualizados.

```python
def apply_theme_for_zellij(self, zellij_name: str | None) -> None:
    self.register_zellij_themes()  # rebuild "current" desde alacritty
    if self.theme != "current":
        self.theme = "current"
    else:
        self._watch_theme("current")  # fuerza re-render
```

### 4. Refresh en Color Editor

Hoy el Color Editor no notifica al TUI cuando guarda. Agregar:
en `action_save` del color editor, llamar a `register_zellij_themes`
+ `apply_theme_for_zellij(None)` para refrescar.

### 5. Limpieza

Eliminar `build_textual_theme(theme: ZellijUITheme)` y
`build_textual_theme_from_legacy(name, slots)` — ya no se usan para
el TUI. `_derive_slots` y `derive_legacy_slots_from_bundled` siguen
usandose para el sync Alacritty y para clones, pero NO para construir
Textual themes.

Tests afectados:
- `test_textual_theme_uses_white_slot_for_foreground`
- `test_build_textual_theme_dracula`
- `test_build_textual_theme_catppuccin_latte_marks_light`
- `test_build_textual_theme_returns_none_for_invalid`
- `test_build_textual_theme_from_legacy_basic`
- `test_build_textual_theme_from_legacy_missing_fg_or_bg_returns_none`
- `test_all_bundled_themes_build_valid_textual_themes`
- `test_app_registers_bundled_and_user_themes`
- `test_app_applies_active_zellij_theme_on_mount`
- `test_theme_picker_apply_changes_textual_theme`

Estos tests dejan de tener sentido en su forma actual porque ya no
hay un Textual theme por tema Zellij. Hay que refactorizarlos para
verificar que:
- El theme "current" se registra a partir de alacritty.toml.
- Tras aplicar un tema Zellij, "current" tiene los nuevos hex.
- Tras editar Alacritty, "current" tiene los nuevos hex.

## Open questions

1. **Nombre del Textual theme** — `"current"`, `"alacritty"`, o el
   nombre del tema Zellij activo (que siempre se reapunta a
   alacritty)? Mi sugerencia: `"current"`. Es claro que no es un
   tema fijo sino el estado actual.

2. **Comportamiento de Ctrl+P (paleta de comandos)** — hoy lista
   todos los temas registrados. Con un solo "current", la paleta
   solo mostrara "current" y los textual built-in stock. ¿Esta bien
   asi, o se mantiene el listado por familia visual?

   Mi sugerencia: dejarlo asi. Ctrl+P no es la via natural para
   cambiar tema en este TUI — la pantalla de Temas Zellij lo es.

3. **Que pasa con NON_CLONEABLE_THEMES y los overrides** — siguen
   afectando solo a la sincronizacion Alacritty (porque alli es
   donde se usan los slots derivados). El TUI ya no los usa. No
   cambia nada para ellos.

4. **¿Y si alacritty.toml no existe o le falta primary?** Fallback:
   no registrar "current", el TUI usa textual-dark default. Notify
   al usuario una vez al startup.

## Plan de ejecucion

Lo dividiria en 3 commits incrementales:

1. **commit 1**: agregar `build_textual_theme_from_alacritty`,
   modificar `register_zellij_themes` y `apply_theme_for_zellij`.
   Tests: agregar nuevos que verifiquen el nuevo comportamiento, los
   viejos los dejo pasar (la mayoria seguiran pasando porque el theme
   sigue cambiando al aplicar — solo que ahora viene de alacritty).

2. **commit 2**: refresh del TUI en el Color Editor al guardar.
   Test: editar slot de Alacritty, guardar, verificar que el TUI
   tiene el nuevo color.

3. **commit 3**: limpieza. Eliminar funciones que ya no se usan.
   Refactor de tests obsoletos. Update NOTES.md.

## Trade-offs

A favor:
- TUI siempre matchea terminal — coherencia visual total.
- Single source of truth (alacritty.toml).
- Simplifica el codigo (una funcion en vez de tres).
- Ya tenemos infraestructura para detectar cambios en Alacritty.

En contra:
- Cada tema Zellij ya no tiene "su" personalidad en el TUI. Todos
  los temas dark se ven con primary blue (ANSI normal.blue), todos
  los light tambien. Pierdes la decision artistica de cada autor.
- Si dos temas Zellij tienen el mismo `normal.blue` en alacritty
  (por sync con la misma paleta), el TUI los muestra identicos.
- Ctrl+P pierde el listado de temas para previsualizacion.

## Resumen

Cambio bien delimitado: una funcion nueva, dos modificadas, una serie
de tests que se actualizan. Aproximadamente 1 sesion de trabajo. El
resultado: el TUI deja de "saber" sobre Zellij themes para su propia
estilizacion — solo lee Alacritty. Cuando Alacritty cambia (por
sync de tema o edicion manual), el TUI cambia.
