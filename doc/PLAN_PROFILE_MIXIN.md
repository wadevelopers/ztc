# PLAN: extraer lógica de Load/Save a `ProfileEditingMixin`

**Status**: DRAFT — pendiente de decisión sobre forma técnica.

---

## Contexto y motivación

`ColorEditorScreen` y `TerminalSettingsScreen` editan ambos el **mismo
archivo de configuración del backend** (`alacritty.toml` / `kitty.conf`)
desde dos pantallas distintas. La única diferencia real entre las dos
es **qué filas renderizan** y cómo se edita una fila:

- `ColorEditorScreen`: filas con `nombre + hex + swatch`. Modal de
  edición de color con preview.
- `TerminalSettingsScreen`: filas con `nombre + valor`. Modal según
  kind (enum picker, font picker, prompt).

Pero **toda la mecánica de carga, guardado, switching de perfil y
conversión a manifest es idéntica** entre las dos. Hoy está duplicada:
8 métodos casi línea-por-línea iguales.

### Métodos duplicados

| Método | Función |
|---|---|
| `action_load` | Maneja `l`: dirty check + delega a `_prompt_load_profile`. |
| `_prompt_load_profile` | Pide path con `PromptModal`, valida, delega a `_do_load`. |
| `_do_load` | Convert silencioso si hace falta, load doc, `set_active_profile`, update state, toast con backup. |
| `action_save` | Maneja `s`: abre `PromptModal` prellenado con nombre actual, branch in-place / unmanage / save-as. |
| `_save_in_place` | `save_profile_with_reload`, toast. |
| `_save_unmanage` | `unmanage_manifest`, recarga doc, sync state, toast con backup. |
| `_save_as` | Convert silencioso si hace falta, `backend.save`, `set_active_profile`, toast con backup. |
| `action_back` | Maneja `esc`: dirty check + pop screen / save in-place + pop. |

### Evidencia del problema

En esta sesión ya pasaron **3 bugs/cambios que tuvimos que aplicar dos
veces** por la duplicación:

1. Guard `path == manifest_path` en `_prompt_load_profile`.
2. Llamada `_save_in_place` directa en `UnsavedChangesModal.save` (para
   no abrir un segundo modal).
3. Branch `_save_unmanage` cuando `new_path == manifest_path`.

Si no consolidamos, la próxima feature de profiles (ej. un selector
gráfico de perfiles vía Load) requiere implementar dos veces y los
backends se desincronizan eventualmente.

---

## Scope

### Ubicación

`src/ztc/screens/profile_editing.py` — junto a las screens consumidoras.

**No** en `services/`: el mixin abre modales (`PromptModal`,
`ConfirmActionModal`, `UnsavedChangesModal`), llama a
`self.app.push_screen` y `self.app.notify`, maneja `self.dirty` y
callbacks Textual. Es lógica de pantalla, no service puro.

### Lo que entra al mixin

Los 8 métodos arriba + un **hook opcional** para que las screens
puedan reaccionar a cambios de perfil:

```python
class ProfileEditingMixin:
    """Lógica compartida de Load/Save de perfiles.

    Espera que la screen subclase defina:
      - self.backend         (TerminalBackend)
      - self.backend_path    (Path)
      - self.doc             (BackendDoc)
      - self.dirty           (bool)
      - self._refresh_header()
      - self._rebuild_list()

    Opcional: override `_refresh_profile_view()` para hooks extra (ej.
    refrescar warnings de contraste). El mixin la llama tras Load,
    Save-as, Save-unmanage.
    """

    def _refresh_profile_view(self) -> None:
        """Hook llamado tras cambios de perfil/path/doc. Default:
        refresh header + rebuild list. Subclases pueden override +
        super()._refresh_profile_view().

        Nota sobre el nombre: en Load y Unmanage el doc se reemplaza;
        en Save-as solo cambia `backend_path` (el doc in-memory queda).
        El hook se llama en los tres casos porque la UI necesita
        sincronizarse (header, posiblemente warnings). El costo de
        `_rebuild_list` cuando el doc no cambió es trivial (las mismas
        filas) — no vale la pena dividir en dos hooks distintos."""
        self._refresh_header()
        self._rebuild_list()
```

`ColorEditorScreen._refresh_profile_view` override:
```python
def _refresh_profile_view(self) -> None:
    super()._refresh_profile_view()
    self._refresh_warnings()
```

### Lo que NO entra al mixin

- `compose`, `on_mount`: específicos.
- `_rebuild_list`, `_show_detail_at`, `_refresh_header`: específicos
  (la forma de la fila difiere).
- `_refresh_warnings`: específico de ColorEditor.
- `action_reset`, `action_edit`, `action_reload`: específicos (operan
  sobre slots vs settings).

### Limpiezas adicionales en el mismo commit

Mientras tocamos el área, eliminar texto inútil. Verificado contra el
código:

| Texto | Ubicación | Razón |
|---|---|---|
| `"Enter to edit."` / `"Enter to set."` | `color_editor.py:172,176` | Ruido — igual para todas las settings, el binding ya está en footer. |
| `"OK  ->  {normalized}"` | `confirm.py:682` | El swatch preview ya muestra el color final normalizado; el texto duplica info visualmente. |
| `"Hex: #rgb, #rrggbb or #rrggbbaa"` | `confirm.py:634` | El placeholder `#1e1e2e` ya muestra el formato. |

**Lo que se preserva** (verificado por separado):
- El swatch preview en `EditColorModal` (línea 640) — es color, el
  preview vale, no complica.
- `"Invalid format"` (línea 685) — feedback útil de validación.

**Nota sobre `"OK -> {normalized}"`**: una revisión externa argumentó
mantenerlo porque muestra la normalización (`#fff` → `#ffffff`,
mayúsculas → minúsculas) antes de aplicar. El hallazgo es real (sí
tiene esa función), pero la rechazamos: el swatch ya pinta el color
final con `[on {normalized}]` — el user ve el resultado normalizado
visualmente, el texto repite info en formato menos útil. Decisión
del usuario tras evaluación de uso real.

---

## Decisión abierta: forma técnica del helper compartido

Tres opciones plausibles. La decisión condiciona testabilidad,
ergonomía de uso, y cómo se integra si después se hace el refactor
mayor (fusionar Colors + Settings en una sola screen).

### Opción A — Clase mixin (Python multiple inheritance)

```python
class ProfileEditingMixin:
    def action_load(self) -> None: ...
    def action_save(self) -> None: ...
    # ...

class ColorEditorScreen(ProfileEditingMixin, Screen[None]):
    ...

class TerminalSettingsScreen(ProfileEditingMixin, Screen[None]):
    ...
```

**Pros**:
- Acceso natural a `self.doc`, `self.dirty`, `self.backend`, `self.app`.
  Cero boilerplate por método.
- Patrón idiomático en Textual y Django (FormMixin, ListMixin, etc.).
- Las `BINDINGS` y `action_*` se heredan transparentemente: el binding
  `l` apunta a `action_load` del mixin sin ningún glue.
- Override fácil del hook `_refresh_profile_view` con `super()`.

**Contras**:
- Herencia múltiple en Python a veces complica MRO si hay choques de
  método. Acá no hay choque previsible (la base es `Screen`), pero es
  vigilable.
- Las dependencias implícitas (qué atributos espera) están solo en
  docstring. Si la screen no define `self.dirty`, el error explota en
  runtime, no en mypy.

### Opción B — Módulo helper funcional

```python
# src/ztc/screens/profile_actions.py
def action_load(screen: Screen) -> None: ...
def action_save(screen: Screen) -> None: ...

# screens
class ColorEditorScreen(Screen[None]):
    BINDINGS = [Binding("l", "load", "Load"), ...]
    def action_load(self) -> None:
        profile_actions.action_load(self)
```

**Pros**:
- Sin herencia múltiple, sin MRO.
- Funciones puras testeables fuera de Pilot con stubs ligeros.
- Las dependencias son explícitas en cada call (el `screen` param).

**Contras**:
- Boilerplate por método en cada screen (un `action_load` que solo
  delega).
- Las funciones acceden a internals de la screen
  (`screen.doc`, `screen.backend`, ...) — mismo acoplamiento que el
  mixin, sin ventaja de tipado real (Python no obliga signatures).
- Las bindings necesitan `action_*` en la screen igual; el módulo solo
  tiene la implementación.

### Opción C — Controller compuesto

```python
class ProfileController:
    def __init__(self, screen: Screen) -> None:
        self.screen = screen

    def load(self) -> None: ...
    def save(self) -> None: ...

class ColorEditorScreen(Screen[None]):
    def __init__(self, ...):
        super().__init__(...)
        self.profile = ProfileController(self)
    def action_load(self) -> None:
        self.profile.load()
```

**Pros**:
- Composición sobre herencia (principio OO clásico).
- Testeable: el controller se instancia con un mock screen.
- Estado del controller puede tener cosas propias si vale la pena.

**Contras**:
- Doble indirección (`screen.profile.load()`).
- El controller no tiene estado propio relevante — solo accede al
  screen. Es básicamente la opción B con un puntero `self` implícito.
- Boilerplate de instanciar + delegar en cada screen.

### Mi recomendación

**Opción A (mixin)** por simpleza y patrón conocido. El acoplamiento
es el mismo en las tres opciones (todas acceden a `self.doc`,
`self.dirty`, etc.); la pregunta real es si pagamos boilerplate por
explicitud (B/C) o aceptamos implícito por economía de código (A). En
un proyecto de 1 desarrollador con dos screens consumidoras, el
boilerplate de B/C no compra nada que A no tenga.

**Pendiente**: decisión del usuario antes de codear.

---

## Plan de ejecución

Después de elegir la forma:

1. **Crear el helper compartido** (`src/ztc/screens/profile_editing.py`
   si se elige A; ubicación equivalente en `screens/` para B/C — ver
   ajuste de ubicación en "Lo que entra al mixin").
2. **Migrar `ColorEditorScreen`**: usar el helper, eliminar los 8
   métodos locales, mantener `_refresh_profile_view` override que llama
   a `_refresh_warnings`.
3. **Migrar `TerminalSettingsScreen`**: idem sin el override.
4. **Limpiezas de texto**: 3 edits puntuales (color_editor.py + confirm.py).
5. **Tests**: los tests existentes deben seguir pasando sin cambios
   (los métodos se llaman igual desde el binding `l`/`s`/`esc`). Si
   alguno mockeaba el método interno, ajustar el mock al nuevo location.
6. **Smoke manual**: Load + Save + Save-as + unmanage + Save-back + Esc
   con cambios pending, en ambas screens.

Estimación: 1 commit. ~150 líneas eliminadas netas (8 métodos × 2
screens, menos el mixin que las absorbe).

---

## Compatibilidad con refactor futuro (fusionar Colors + Settings)

Si más adelante se decide fusionar `ColorEditorScreen` y
`TerminalSettingsScreen` en una sola pantalla, el mixin se reutiliza
sin cambios — la screen fusionada lo extiende igual, agrega su propio
`_rebuild_list` que renderiza colors+settings juntos, y eso es todo.

De hecho hacer este mixin **antes** del refactor de fusión simplifica
ese trabajo posterior: la screen fusionada no tiene que decidir cómo
unificar la lógica de Load/Save (ya está unificada).

---

## Riesgos

1. **Override sutil de bindings**: las screens hoy declaran
   `BINDINGS = [Binding("l", "load", ...), ...]`. Si el mixin no
   declara BINDINGS y solo aporta `action_load`, las screens siguen
   funcionando porque su BINDINGS apunta a la acción heredada. Pero si
   alguien remueve `Binding("l", "load", ...)` de las screens, no hay
   binding. Mitigación: dejar `BINDINGS` en cada screen (es UI, no
   lógica).

2. **MRO en `Screen[None]`**: si Textual `Screen` tiene un
   `action_load` interno con otro propósito, el mixin lo pisa. No
   parece ser el caso (chequeado: `action_*` en Textual son convención
   de bindings, no nombres reservados). Verificar al integrar.

3. **`self.app` vs `self.app: TermConfigApp`**: el mixin va a llamar a
   `self.app.set_active_profile(...)`. Textual tipa `self.app` como
   `App`, no como `TermConfigApp`. Hoy las screens hacen el cast
   implícito (mypy lo deja pasar). Si pasamos a strict typing, hay que
   cast explícito o asumir un protocolo. Mantenerlo implícito como hoy.

---

## Pendiente antes de codear

- [ ] Decisión sobre forma técnica (A / B / C).
- [ ] Confirmar nombre `ProfileEditingMixin` si se elige A; equivalentes
      para B/C (`profile_actions` módulo / `ProfileController` clase).
