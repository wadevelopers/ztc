# Plan: Terminal settings (modulo comun cross-backend)

> **Prerequisito**: [`PLAN_CONSOLIDATE_ZELLIJ_THEMES.md`](PLAN_CONSOLIDATE_ZELLIJ_THEMES.md) ejecutado y cerrado. Este plan asume:
> - `CanonicalSlot`, `is_valid_hex`, `compute_warnings`, etc. ya viven en `ztc.services.colors`.
> - Stuff de Zellij ya vive en `ztc.zellij.X` (sin paquete pip separado `zellij-themes`).
> - `pyproject.toml` ya no tiene la dep path `zellij-themes`.
>
> **Iteracion 1 (este plan)**: 6 settings con mapeo limpio entre Alacritty y Kitty.
> **Iteracion 2 (otro plan, pendiente)**: blinking, save_to_clipboard, decorations, dynamic_title — cada uno tiene matices que requieren decision (transformacion de tipos, semantica distinta, valores no soportados por algun backend). Las decisiones tentativas estan registradas en la conversacion del 2026-05-08; cuando se aborde iteracion 2, partir desde alli.

## Contexto y motivacion

`ztc` ya tiene infraestructura para editar **colores** de terminal de forma cross-backend (Alacritty TOML y Kitty conf): `TerminalBackend` Protocol, `CanonicalSlot`, `read_slot`/`write_slot`/`delete_slot`/`supported_slots`. La UI consume eso via `ColorEditorScreen`.

Falta cubrir las **otras opciones** comunes a ambas terminales (padding, opacidad, fuente, cursor). Hoy el usuario tiene que editar el archivo a mano. Este plan agrega un modulo paralelo a colores: `TerminalSettingsScreen` con la misma arquitectura, reusando el patron de backend.

El enfoque es deliberadamente **conservador**: solo settings con mapeo 1:1 limpio entre los dos backends en esta iteracion. Lo que tiene matices semanticos (blinking apps-override, copy-on-select primary vs clipboard, decorations parciales en Kitty, dynamic_title sin equivalente) queda para iteracion 2.

## Alcance

### Adentro (iteracion 1)

| Setting | Tipo | Alacritty | Kitty |
|---|---|---|---|
| **padding x** | int (>= 0) | `[window.padding] x = N` | `window_padding_width` (2do valor — Kitty con 2 vals es `vertical horizontal`) |
| **padding y** | int (>= 0) | `[window.padding] y = N` | `window_padding_width` (1er valor — `vertical`) |
| **opacity** | float (0.0..1.0) | `[window] opacity = F` | `background_opacity F` |
| **font size** | float (>= 1.0) | `[font] size = F` | `font_size F` |
| **font family** | str | `[font.normal] family = "S"` | `font_family S` |
| **cursor shape** | enum {Block, Beam, Underline} | `[cursor.style] shape = "S"` | `cursor_shape S` |

**Operaciones soportadas**:
- **read** / **write** del setting actual.
- **reset** (`x`): hace `delete_setting()` — elimina la entrada del archivo. No escribe el default explicito; deja que el terminal use su propio default. Mismo patron que `ColorEditorScreen` con slots: borrar la entrada y dejar al terminal/sistema decidir. El `default` del catalogo queda solo como **hint visual** en la UI ("este setting estaria en X si lo unset").
- **reload** (re-leer del disco).
- **save** (`backend.save(doc, path)` que internamente hace backup, mismo patron que `ColorEditorScreen`).
- **import** (`i`): lee otro archivo del **mismo backend activo** (Alacritty `.toml` desde Alacritty, Kitty `.conf` desde Kitty), extrae las settings que `supported_settings()` reconoce, y las escribe en el doc actual. **No es cross-backend** — esta iteracion no intenta importar Kitty desde Alacritty ni viceversa (Fase ulterior si se necesita).

### Afuera (iteracion 1)

- **blinking**: bool↔intervalo + matiz "apps pueden override por DECSCUSR". Pendiente de iteracion 2.
- **save_to_clipboard / copy_on_select**: semantica de primary/clipboard distinta entre OS y entre backends. Pendiente.
- **decorations**: Alacritty tiene 4 valores (2 macOS-only); Kitty tiene 3 (incluye `titlebar-only` que Alacritty no). Reduccion a bool simple posible pero pierde flexibilidad. Pendiente.
- **dynamic_title**: sin equivalente directo en Kitty (es comportamiento default sin toggle). Pendiente — probablemente como Alacritty-only con disabled-per-backend.

### Otras terminales

Fuera de scope para este plan. Si se agrega Ghostty u otra terminal de archivo plano, el patron de mapeo `_CANONICAL_TO_X_SETTING` se replica trivialmente. GNOME Terminal (dconf), iTerm2 (plist), Wezterm (Lua) requieren infraestructura distinta — no aplican a este patron.

## Decisiones de diseno

### 1. `CanonicalSetting` con tipo y default

A diferencia de `CanonicalSlot` (siempre string hex), las settings son heterogeneas. Modelarlas como dataclass:

```python
# ztc/services/terminals/settings.py

from enum import Enum
from dataclasses import dataclass

class SettingKind(Enum):
    INT = "int"          # padding
    FLOAT = "float"      # opacity, font_size
    STR = "str"          # font_family
    ENUM = "enum"        # cursor_shape

@dataclass(frozen=True)
class CanonicalSetting:
    name: str            # identificador estable: "window.padding.x"
    kind: SettingKind
    default: object      # tipo segun kind
    enum_values: tuple[str, ...] = ()   # solo para ENUM

# Catalogo de settings soportados
SETTINGS = {
    "window.padding.x": CanonicalSetting("window.padding.x", SettingKind.INT, 0),
    "window.padding.y": CanonicalSetting("window.padding.y", SettingKind.INT, 0),
    "window.opacity": CanonicalSetting("window.opacity", SettingKind.FLOAT, 1.0),
    "font.size": CanonicalSetting("font.size", SettingKind.FLOAT, 12.0),
    "font.family": CanonicalSetting("font.family", SettingKind.STR, "monospace"),
    "cursor.shape": CanonicalSetting(
        "cursor.shape", SettingKind.ENUM, "Block",
        enum_values=("Block", "Beam", "Underline"),
    ),
}
```

El **valor canonico** (lo que viaja por la API) usa el tipo Python natural: `int` para padding, `float` para opacity, `str` para family, str enum (con valores normalizados) para shape.

**Normalizacion de enum**: usamos los valores capitalizados de Alacritty (`"Block"`, `"Beam"`, `"Underline"`) como canonicos. Kitty acepta minusculas (`block`, `beam`, `underline`); el backend Kitty hace la conversion al leer/escribir.

**Validacion centralizada en `settings.py`**: la coercion y validacion viven en el catalogo, no replicada en cada backend ni en la UI. Dos helpers publicos:

```python
def coerce_setting_value(setting: CanonicalSetting, raw: object) -> object | None:
    """Toma un valor crudo (lo que devuelve el parser TOML/conf) y lo
    convierte al tipo canonico de la setting. Devuelve None si no se
    puede coercionar limpio (ej. font_size = "abc"). Sin excepciones —
    los backends propagan None y la UI muestra "unset"."""

def validate_setting_value(setting: CanonicalSetting, value: object) -> bool:
    """True si value es valido segun setting.kind y restricciones
    (rango para INT/FLOAT, enum_values para ENUM, no-vacio para STR).
    Lo usa la UI antes de habilitar el boton "Guardar"."""
```

Asi UI, import y backends consultan la misma fuente de verdad. Si despues se cambia un rango (ej. opacity 0..1 → 0..2), se cambia en un solo lugar.

### 2. Extension de `TerminalBackend`

Protocol nuevo (al lado del existente para slots):

```python
class TerminalBackend(Protocol):
    # ... metodos existentes (read_slot/write_slot/...) ...

    # Nuevos
    def read_setting(
        self, doc: BackendDoc, setting: CanonicalSetting
    ) -> object | None:
        """Devuelve el valor actual del setting (tipo segun setting.kind),
        o None si no esta definido en el archivo."""

    def write_setting(
        self, doc: BackendDoc, setting: CanonicalSetting, value: object
    ) -> None:
        """Escribe value en el archivo con el formato propio del backend.

        Antes de escribir, llama a `validate_setting_value(setting, value)`
        y levanta `ValueError` si el valor no es valido (rango, kind,
        enum). Asi la validacion vive en un solo lugar (el catalogo) y
        no depende solo de la UI — un caller programatico tampoco puede
        meter basura en el archivo.
        """

    def delete_setting(
        self, doc: BackendDoc, setting: CanonicalSetting
    ) -> bool:
        """Elimina la entrada del archivo. Devuelve True si existia."""

    def supported_settings(self) -> list[CanonicalSetting]:
        """Lista de settings que este backend soporta. En iteracion 1
        ambos backends soportan los 6; en iteracion 2 algunos pueden
        diferir (ej. dynamic_title solo Alacritty)."""
```

### 3. Mapeo por backend

Cada backend tiene su tabla `_CANONICAL_TO_X_SETTING`:

```python
# alacritty.py
_CANONICAL_TO_ALACRITTY_SETTING = {
    "window.padding.x": ("window", "padding", "x"),  # path TOML
    "window.padding.y": ("window", "padding", "y"),
    "window.opacity": ("window", "opacity"),
    "font.size": ("font", "size"),
    "font.family": ("font", "normal", "family"),
    "cursor.shape": ("cursor", "style", "shape"),
}

# kitty.py
_CANONICAL_TO_KITTY_SETTING = {
    "window.padding.x": "window_padding_width",  # caso especial: 1 o 2 ints
    "window.padding.y": "window_padding_width",  # mismo key, segundo valor
    "window.opacity": "background_opacity",
    "font.size": "font_size",
    "font.family": "font_family",
    "cursor.shape": "cursor_shape",
}
```

#### Caso especial: `window_padding_width` en Kitty

Kitty acepta el padding **en pts** con 1, 2, 3 o 4 valores (verificado en `man kitty.conf`):

- 1 valor: los 4 lados.
- 2 valores: vertical horizontal.
- 3 valores: top horizontal bottom.
- 4 valores: top right bottom left.

Para mapear `padding.x` / `padding.y` (estilo Alacritty con 2 valores horizontal/vertical):

- **Read**:
  - 1 valor: devolverlo para ambos `x` y `y`.
  - 2 valores: el primero es `y` (vertical), el segundo es `x` (horizontal).
  - 3 o 4 valores: si la simetria se respeta (`top == bottom` para `y`; `left == right` para `x`), devolver `(x, y)` correspondientes. Si NO se respeta (asimetrico, no representable en el modelo de 2 valores Alacritty), devolver **`None`** (= "unset" en la UI) — es la opcion conservadora: no perdemos datos del archivo (el `delete_setting` solo se ejecuta con `x`), pero el UI no muestra un valor enganoso.
- **Write**: emitir `window_padding_width Y X` (2 valores: vertical horizontal). Sobrescribe cualquier configuracion de 3 o 4 valores que hubiera, con perdida controlada (decision del usuario al editar desde el UI).
- **Tipos**: el canon es `int` (por consistencia con Alacritty que requiere int). Kitty acepta floats (pts), pero si el archivo tiene `window_padding_width 2.5` el `coerce_setting_value` devuelve `None` (= "unset" en UI). Igual que con asimetria: no se pierde el archivo, simplemente no se representa en el UI hasta que el usuario sobrescriba.

### 4. UI: `TerminalSettingsScreen`

Nuevo screen `ztc/screens/terminal_settings.py` con la misma estructura que `ColorEditorScreen`:

- Header con backend detectado.
- Lista de settings (cada uno con label, valor actual, default).
- Modal de edicion segun kind: input numerico para INT/FLOAT, input de texto para STR, picker de opciones para ENUM.
- Bindings: `Enter` editar, `x` resetear al default, `s` guardar, `i` importar, `r` reload, `Esc` salir.
- Backup automatico antes de guardar (mismo helper que ColorEditor).
- Item nuevo en menu principal de ztc: **"Terminal settings"** (justo despues de "Terminal colors"), gateado por backend disponible (mismo patron que colors).

### 5. Donde vive el catalogo `SETTINGS`

`CanonicalSlot` ya esta en `ztc.services.colors` despues del prerequisito. El catalogo `SETTINGS` y `CanonicalSetting` viven al lado de los backends que los consumen, en `ztc/services/terminals/settings.py`. Coherente con los backends que ya viven en `ztc/services/terminals/`.

## Pasos de ejecucion

### Fase 1: Catalogo + extension de backends

1. Crear `ztc/services/terminals/settings.py` con `CanonicalSetting`, `SettingKind`, y el dict `SETTINGS` (los 6 de iteracion 1).

2. Extender `ztc/services/terminals/__init__.py` (`TerminalBackend` Protocol) con los 4 metodos nuevos.

3. **`AlacrittyBackend`** (`alacritty.py`):
   - Agregar `_CANONICAL_TO_ALACRITTY_SETTING`.
   - Implementar `read_setting`, `write_setting`, `delete_setting`, `supported_settings`.
   - Helpers internos para navegar el TOML por path (re-usar lo que ya hay en `read_slot` si aplica, o duplicar si la estructura difiere; preferir reuso).

4. **`KittyBackend`** (`kitty.py`):
   - Agregar `_CANONICAL_TO_KITTY_SETTING`.
   - Implementar los 4 metodos. Caso especial de `window_padding_width` (read/write con 1-4 valores).
   - Quote handling para `font_family` con espacios (Kitty no requiere comillas, valor literal hasta fin de linea; Alacritty requiere comillas en TOML).

5. **Tests**:
   - `tests/test_terminal_alacritty_settings.py`: leer/escribir cada uno de los 6 settings, roundtrip read→write→read, delete, valores invalidos.
   - **TOML inline tables**: el TOML de Alacritty puede expresar las tablas como `[window.padding]` con keys debajo, o inline `padding = { x = 8, y = 8 }`. Tests deben cubrir las dos formas — tanto al leer (parser ve ambas equivalentes) como al escribir (preservar la forma existente si el usuario ya tiene inline). Aplica especialmente a `padding`, `cursor.style`, `font.normal`.
   - `tests/test_terminal_kitty_settings.py`: idem para Kitty.
   - Tests del caso especial `window_padding_width`: archivo Kitty con 1, 2, 3 y 4 valores; verificar lectura simetrica (devuelve `(x, y)`) vs asimetrica (devuelve `None`); con valores `int` vs `float` (coercionar limpio o `None`).

6. **Commit**: `feat: extender TerminalBackend con read_setting/write_setting (catalogo de 6 settings)`.

### Fase 2: `TerminalSettingsScreen`

1. Crear `ztc/screens/terminal_settings.py`. Estructura analoga a `ColorEditorScreen`:
   - `compose`: header + OptionList con los settings.
   - Handlers: edicion, reset, save, import, reload.
   - Modales: `IntInputModal`, `FloatInputModal`, `StrInputModal` (algunos pueden reusarse o crearse nuevos), `EnumPickerModal`.
   - Para guardar reusar el patron real del repo: `backup = self.backend.save(self.doc, self.backend_path)` (mismo patron que `color_editor.py:309`). Cada backend (Alacritty/Kitty) maneja internamente el backup atomico antes de escribir.

2. **Tests**:
   - `tests/test_terminal_settings_screen.py`: smoke test con Pilot, edicion de cada tipo, save crea backup.

3. **Commit**: `feat: TerminalSettingsScreen para editar padding/opacity/font/cursor en backends comunes`.

### Fase 3: Item en menu principal de ztc

1. Agregar `Option("Terminal settings", id="terminal-settings", disabled=...)` en `_build_menu_options()`, **inmediatamente despues** de "Terminal colors". Mismo gating que el item de colors (backend disponible, no SSH).
2. Branch nuevo en `_on_menu_selected` que monta `TerminalSettingsScreen`.
3. Actualizar tests del menu para esperar 5 items en happy path.
4. **Commit**: `feat: agregar item 'Terminal settings' al menu principal`.

### Fase 4: Verificacion manual + README

1. Lanzar `ztc` con Alacritty y con Kitty, verificar:
   - Apertura del screen sin errores.
   - Edicion de cada setting reflejada en el archivo (con backup).
   - Import desde otro archivo: lee solo settings conocidos.
   - Reset al default funciona.
2. Actualizar `README.md` con la mencion del nuevo item.
3. **Commit**: `docs: README con Terminal settings item`.

## Riesgos y consideraciones

### Casos especiales del backend Kitty

- **`window_padding_width` con 1-4 valores**: ver Decision detallada en seccion "Caso especial" mas arriba. Resumen: read devuelve `(x, y)` cuando se puede representar simetricamente con 2 valores; devuelve `None` (= "unset" en UI) cuando hay asimetria o valores no-int. Write emite siempre 2 valores `Y X` (sobreescribe configuraciones de 3/4 valores con perdida controlada).

- **`font_family` con valores que tienen espacios**: en Kitty no se usan comillas (`font_family JetBrains Mono`). En Alacritty si (`family = "JetBrains Mono"`). El backend Kitty preserva la linea entera despues del key; el backend Alacritty maneja TOML.

### Tipos heterogeneos vs API uniforme

El metodo `read_setting` devuelve `object` (puede ser int, float, str). El UI debe reinterpretar segun `setting.kind`. Riesgo: errores de tipo si el archivo tiene un valor mal formado (ej. `font_size abc`). El backend debe validar al parsear y devolver `None` con un log/toast en lugar de crashear.

### Escalabilidad a iteracion 2

El catalogo `SETTINGS` se expande agregando entradas. La API no cambia. La complejidad esta en:
- **blinking**: introducir un nuevo `SettingKind.BOOL` (o representarlo como ENUM de 2 valores), y mapeo bidireccional con transformaciones (Kitty `cursor_blink_interval 0/0.5` ↔ bool; Alacritty `Always`/`Never` ↔ bool).
- **save_to_clipboard**: ENUM de 2 valores (Primary, Primary+Clipboard). Mapeo claro.
- **decorations**: BOOL "show decorations" con mapeo binario.
- **dynamic_title**: BOOL, **soporte solo en Alacritty**. Mejorar `supported_settings()` para que Kitty no la liste.

Iteracion 2 reusa toda la infraestructura de iteracion 1; solo agrega 4 entradas al catalogo + handle de settings backend-specific.

### Default values: `x` hace `delete_setting()` (no escribe el default explicito)

El catalogo declara `default` por setting (`SETTINGS["window.opacity"].default = 1.0`, etc.). El UI muestra el default como **hint visual** cuando el archivo no tiene la entrada. Resetear (`x`) **borra la entrada del archivo** via `delete_setting()` — deja al terminal usar su propio default. Mismo patron que `ColorEditorScreen` con slots: borrar la entrada y no escribir un valor "default" explicito. Es mas limpio (no contamina el archivo con valores que el terminal sabe por si solo) y previene drift (si Alacritty cambia su default en una version, no quedamos pegados al valor que tuvimos en el catalogo).

## Que dejamos sin tocar

- `ztc.zellij.theme_assets`, `config`, `user_themes`, `models`: intactos despues del prerequisito. Este plan no los modifica.
- `ColorEditorScreen` y la API de slots: comportamiento intacto. Settings es paralelo a slots, no overlaps.
- Reordenamiento del menu principal: solo se agrega el item nuevo "Terminal settings".

## Resumen ejecutivo

> Asume el prerequisito (`PLAN_CONSOLIDATE_ZELLIJ_THEMES.md`) ya cerrado. La columna "Antes" refleja el estado **post-consolidacion**, no el estado actual del repo hoy.

| | Antes (post-consolidacion) | Despues iteracion 1 |
|---|---|---|
| Settings editables desde UI | Solo colores | Colores + 6 settings comunes (padding x/y, opacity, font size+family, cursor shape) |
| `TerminalBackend` Protocol | `read_slot`/`write_slot`/`delete_slot`/`supported_slots` | + `read_setting`/`write_setting`/`delete_setting`/`supported_settings` |
| Items en menu principal | 4 (themes, layouts, sessions, colors) | 5 (+ terminal settings) |
| Backends soportados | Alacritty, Kitty | igual (settings funcionan en los 2) |
| Tests | ~265 | ~285 (+ tests de read/write/UI) |
