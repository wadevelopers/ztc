# PLAN: Perfiles de terminal con manifest (Load/Save profile switching) — v2

**Status**: DRAFT v2 — incorpora review externa. Pendiente de aprobación.

**Cambios respecto a v1**:

- Incorporados 4 bloqueantes y 4 menores del review externo (todos
  válidos al verificar contra el código).
- Sección nueva: **Compatibilidad Alacritty vs Kitty** (las dos
  implementaciones tienen mecánica distinta).
- Sección nueva: **Puntos donde mantengo criterio sobre la review**
  con fundamentación técnica.
- Plan reorganizado en fases más granulares (A–I) para acomodar
  startup checks (Kitty) y separación de app state.

**Decisiones aún pendientes**:

- Fase G: estrategia de conversión inicial del archivo default a
  manifest (G1 / G2 / G3).
- Nombre default del primer perfil convertido.
- Confirmar el formato exacto del marcador manifest (TOML vs comentario,
  detalle en Fase A).

---

## Contexto

Origen: armando un script externo (`~/.config/ztc/scripts/main5.sh`) para
lanzar Alacritty con perfil dedicado (`c64.toml`) + Zellij con layout
`c64` sin tocar la config principal del terminal. Funcionó como prueba
puntual, pero quedó claro que el camino limpio es soportar el flujo desde
dentro de ztc:

- Hoy `Save` en `ColorEditorScreen` / `TerminalSettingsScreen` guarda
  siempre al mismo archivo (`backend_path`). No hay forma de "guardar
  como" con otro nombre.
- Hoy `Import` (hotkey `i`) **mergea** valores de un archivo al `doc`
  actual y conserva `backend_path`. No es "abrir como activo".
- El usuario quiere: tener perfiles separados (`c64.toml`, `vga.toml`,
  ...), poder cambiarlos en vivo desde el TUI, y que el cambio se
  refleje **en la ventana de terminal actual** sin reiniciar.

## Decisiones de diseño acumuladas

1. **Scope inmediato = "B" del análisis previo**: doc reframe + Save con
   nombre + Load. El "elegir config al lanzar desde opción `l`" queda
   cubierto naturalmente por este plan (cuando se lanza, el activo
   manda).
2. **Estrategia = Opción 2 (manifest)** sobre Opción 1 (mirror). El
   archivo default se vuelve un manifest que importa el perfil activo.
3. **Semántica de Load = Opción A** (abrir como activo): reemplaza
   `backend_path` runtime, escribe el manifest para apuntar al archivo
   cargado.
4. **Rename**: `Import` → `Load`. Hotkey `i` → `l`. Razón: "import"
   sugiere otro formato y "theme" no es preciso (son colors/settings).
   "Load" es companion natural de "Save".
5. **Reorden de bindings**: `enter, x, r, l, s, esc`. El `enter` no se
   muestra en el footer (es obvio para listas; coherente con el resto
   del proyecto).
6. **Modal de Save**: input prellenado con `backend_path.name`. Foco en
   el input (no en botón). **`PromptModal` actual ya cumple**:
   `Input.Submitted` (Enter desde el input) confirma directo
   (`confirm.py:246-248`). La idea original de "foco al botón" se
   descartó porque resuelve un problema que no existe.

## Hallazgos verificados en el código y en los binarios

- **Alacritty 0.13.2** soporta `[general] import = ["..."]` nativamente.
  Confirmado por `alacritty migrate --skip-imports`. Live-reload del
  archivo default sigue los imports automáticamente.
- **Kitty** soporta `include <path>` nativamente (confirmado por `man
  kitty.conf`). Re-evalúa includes al recibir `kitty @ load-config`.
- **Backend protocol** (`src/ztc/services/terminals/__init__.py:17-112`)
  hoy tiene los métodos esperados (load/save/slots/settings/
  `import_theme_file`/`reload_after_save`/`manual_reload_hint`).
- **`reload_after_save`**: Alacritty retorna `True` directo confiando en
  el watchdog nativo (`alacritty.py:71`); Kitty hace `kitty @
  load-config` vía IPC (`kitty.py:376-406`), con caveat: `opacity` usa
  un IPC adicional (`set-background-opacity`) solo si
  `doc.changed_settings` marca `window.opacity` como cambiada
  (`kitty.py:388-405`).
- **App state `backend_path`** es un slot único en `AppScreen.__init__`
  (`app.py:141-155`). Se pasa por valor al instanciar
  `ColorEditorScreen` (`app.py:388`) y `TerminalSettingsScreen`
  (`app.py:399`). Si una screen muta su `self.backend_path` localmente,
  `AppScreen` y otras screens no se enteran.
- **`theme_sync.sync_terminal_with_zellij_theme`** (`theme_sync.py:111`)
  recibe `backend_path` como argumento del caller — depende del valor
  que el app tenga al momento.
- **`build_startup_check`** (`startup_checks.py:35`) recibe
  `backend_path` y carga/guarda directivas globales (`allow_remote_control`,
  `listen_on`, prefs `# ztc:`) ahí. Si `backend_path` pasa a ser el perfil
  activo, esas directivas viajan con el perfil y se pierden al switch.
- **Kitty backend ya tiene infra de includes** (`kitty.py:13-30`, depth
  limit `_MAX_INCLUDE_DEPTH=5`, preservación al leer).
- **Alacritty backend NO tiene nada sobre imports** —se agrega.
- **Precedente de marcador ztc en archivos de config**: Kitty backend ya
  usa `# ztc:<json>` para preferences (`kitty.py:97`, `read_ztc_pref`,
  `write_ztc_pref`). Es el patrón a seguir para el manifest marker.

---

## Plan por fases

### Fase A — Backend protocol + Alacritty support

Agregar al protocol (`services/terminals/__init__.py`):

- `read_active_profile(manifest_path: Path) -> Path | None` — solo si el
  archivo es un **manifest gestionado por ztc**, devuelve el path del
  perfil activo. Si no, devuelve `None` (significa: este archivo se
  comporta como su propio perfil, no hay switching).
- `write_active_profile(manifest_path: Path, profile_path: Path) -> None`
  — reescribe el manifest para apuntar a `profile_path`. Preserva el
  marcador y el resto del archivo.
- `is_managed_manifest(path: Path) -> bool` — predicado que detecta el
  marcador ztc.
- `reload_after_profile_switch(manifest_path: Path, new_profile_path: Path) -> bool`
  — recarga la terminal viva tras un switch de perfil. Implementación
  detallada en Fase B (Kitty). Alacritty retorna `True` directo
  (live-reload nativo del manifest).
- `reload_after_profile_save(profile_doc: BackendDoc, profile_path: Path, manifest_path: Path) -> bool`
  — recarga la terminal viva tras un save al perfil activo (sin cambio
  de perfil). Para Kitty: igual que `reload_after_save` pero leyendo
  las prefs runtime (`allow_remote_control`, `listen_on`,
  `remote_control_pending_instance`) del manifest, no del
  `profile_doc`. Para Alacritty: `True` directo. Usado por el helper
  `save_profile_with_reload`.
- `convert_to_manifest(path: Path, profile_path: Path) -> Path` —
  **backend-specific**:
  - **Alacritty**: trivial. Mueve todo el contenido actual a
    `profile_path`, deja `path` como manifest con `[ztc]
    managed_manifest = true` + `[general] import = ["..."]`. Backup
    automático.
  - **Kitty**: hace **split**. El manifest CONSERVA las managed
    directives (`allow_remote_control`, `listen_on`,
    `dynamic_background_opacity`) y la línea `# ztc:{...}` con sus
    prefs runtime (`remote_control_pending_instance`,
    `remote_control_modal`, etc.) + agrega `managed_manifest` al JSON +
    agrega `include profile.conf`. El perfil RECIBE colors, settings
    editables y resto de config del usuario (incluyendo includes
    propios del user, comentarios, etc.). Si las managed directives
    fueran al perfil, cambiar de perfil rompería el sistema de hot
    reload introducido en v1.2.0.

  Devuelve el path del backup. Crea backup en ambos backends.

**Formato del marcador** (a confirmar pero recomendado):

- Alacritty: sección TOML `[ztc]` con clave `managed_manifest = true`.
  Tomlkit la preserva. Ejemplo:
  ```toml
  [ztc]
  managed_manifest = true

  [general]
  import = ["c64.toml"]
  ```
- Kitty: clave `managed_manifest` dentro del JSON existente `# ztc:{...}`
  que ya usan las prefs runtime (`read_ztc_pref` / `write_ztc_pref` en
  `kitty.py:322-331`). El marker convive en la misma línea JSON con las
  prefs ya existentes (`remote_control_pending_instance`,
  `remote_control_modal`, etc.). Ejemplo:
  ```
  # ztc:{"managed_manifest": true, "remote_control_pending_instance": "pid:1378080"}
  include c64.conf
  allow_remote_control yes
  listen_on unix:@ztc-{kitty_pid}
  dynamic_background_opacity yes
  ```
  Razón: el parser actual (`_ZTC_PREF_RE = re.compile(r"^# ztc:(.*)$")`
  en `kitty.py:97`) espera JSON después de `# ztc:`. Usar formato
  key=value en una línea aparte rompería ese parser y haría que
  `write_ztc_pref` (que reescribe la línea completa de prefs) borre el
  marker por accidente.

**Detección segura**: `is_managed_manifest(path)` retorna `True` SOLO si
el marcador está presente. Existing `import`/`include` en configs reales
del usuario (sin marcador) **se consideran config standalone**, no
manifest — `read_active_profile()` retorna `None` y el archivo se trata
como hoy.

**Implementación Alacritty** (`services/terminals/alacritty.py`): nuevo.
Usar tomlkit para preservar formato/comentarios.

**Nuevo helper en `services/save_helper.py`** (NO en el protocol —
sigue el patrón de `save_with_reload` existente, que también es helper
que compone `backend.save` + `backend.reload_after_save`):

- `save_profile_with_reload(backend, profile_doc, profile_path, manifest_path) -> SaveResult`
  — guarda `profile_doc` al `profile_path` y dispara reload usando el
  `manifest_path` (necesario en Kitty para leer prefs runtime que viven
  en el manifest, no en el perfil). Composición:
  ```python
  backup = backend.save(profile_doc, profile_path)
  reload_ok = backend.reload_after_profile_save(
      profile_doc, profile_path, manifest_path
  )
  hint = backend.manual_reload_hint() if not reload_ok else None
  return SaveResult(backup, reload_ok, hint)
  ```
  El callsite no tiene que pensar: llama al helper.

### Fase B — Kitty backend: profile switching + reload + opacity

`services/terminals/kitty.py`:

- Implementar los 6 métodos nuevos del protocol (`read_active_profile`,
  `write_active_profile`, `is_managed_manifest`,
  `reload_after_profile_switch`, `reload_after_profile_save`,
  `convert_to_manifest`) adaptando la infra de includes existente.
- **`write_active_profile` toca DOS cosas y preserva el resto**:
  - Reemplaza/agrega la línea `include <profile.conf>` apuntando al
    nuevo perfil (no agrega un include duplicado).
  - Actualiza/agrega la key `managed_manifest` dentro del JSON `# ztc:{...}`
    existente, **preservando íntegras las demás keys**
    (`remote_control_pending_instance`, `remote_control_modal`, etc.).
  - Nunca reescribe la línea `# ztc:{...}` desde cero; siempre hace
    merge en memoria antes de serializar.
- **`write_ztc_pref` ya hace merge correcto**
  (`kitty.py:326-331`: `_read_ztc_dict` lee todas las keys, agrega la
  nueva sin tocar las otras, reescribe la línea con todas). **No
  requiere cambio de código**. Acción correspondiente: **test** que
  verifica que escribir `remote_control_modal` o
  `remote_control_pending_instance` no borra `managed_manifest`.
- **Helper `save_profile_with_reload` (en `save_helper.py`, NO método
  del backend)**: declarado en Fase A. Su rol es componer
  `backend.save(profile_doc, profile_path)` + reload que mire el
  manifest. La parte backend-specific del reload sí va al protocol como
  método nuevo:
  - **Nuevo método del protocol** `reload_after_profile_save(profile_doc, profile_path, manifest_path) -> bool`:
    para Kitty, igual que `reload_after_save` pero leyendo las prefs
    runtime (`allow_remote_control`, `listen_on`,
    `remote_control_pending_instance`) del **manifest** en lugar del
    `profile_doc`. Sin esto, `reload_after_save` mira el doc del perfil,
    no encuentra esas keys, y bailea con `return False`
    (`kitty.py:380-387`) — el reload IPC nunca dispara aunque el
    manifest esté correctamente configurado.
  - Para Alacritty: retorna `True` directo (live-reload nativo del
    manifest cubre el caso post-save al perfil).
- **`reload_after_profile_switch(manifest_path, new_profile_path) -> bool`**
  (método del protocol, declarado en Fase A). Para Kitty:
  - Hace `kitty @ load-config` (que re-evalúa includes).
  - **Opacity: simplificación pragmática**. El orden transaccional de
    `set_active_profile` (Fase C) hace que cuando este método se invoca,
    el manifest YA esté reescrito apuntando al nuevo perfil — no
    tenemos acceso al estado pre-switch para comparar opacity. En lugar
    de complicar la API pasando paths anteriores, **siempre disparar
    `set-background-opacity` post-`load-config` con la opacity efectiva
    actual** (calculada desde manifest + includes resueltos). Es
    idempotente — si la opacity ya es la que está en el archivo, el
    IPC no cambia nada visible. Más simple, más robusto.
  - Si la opacity efectiva no es float (config rara, opacity no
    seteada): solo `load-config`, skip `set-background-opacity`.
- Para Alacritty: retorna `True` directo (live-reload nativo del
  manifest dispara solo).
- **`theme_sync.sync_terminal_with_zellij_theme`** (`theme_sync.py:111`)
  actualmente usa `save_with_reload` y su firma solo recibe
  `backend_path`. Cambios necesarios:
  - **Agregar `manifest_path: Path | None = None`** a la firma. Si es
    `None`, comportamiento como hoy (no hay profile-switching activo).
    Si está, lo pasa a `save_profile_with_reload` para que el reload de
    Kitty lea prefs runtime del lugar correcto.
  - **Actualizar callers**: `AppScreen` (o quien dispare la sync) resuelve
    el `manifest_path` desde su estado (`self.backend_manifest_path`)
    antes de invocar, y se lo pasa explícito.
  - Default `None` permite que tests existentes y código que aún no
    conozca el concepto sigan operando sin cambios.
- Verificación obligatoria en Fase A/B: comprobar en runtime que `kitty
  @ load-config` efectivamente re-evalúa includes (no asumirlo). Si no,
  hay que enviar comandos adicionales o cargar el include explícitamente
  via `kitty @ load-config <profile_path>`.

**Alacritty** no necesita la mecánica de reload: live-reload nativo
cubre el switch (re-lee el manifest, sigue el import). Por simetría del
protocol:

- `save_profile_with_reload` en Alacritty es equivalente a
  `save_with_reload` (no necesita el manifest para nada — el live-reload
  nativo del manifest dispara solo después).
- `reload_after_profile_switch` retorna `True` directo.

### Fase C — App state: separación manifest / active profile

`src/ztc/app.py`:

- Cambio en `AppScreen.__init__`:
  - `self.backend_manifest_path: Path | None` — siempre el archivo
    default (`backend.default_config_path()`).
  - `self.backend_path: Path | None` — el perfil activo. Inicialmente
    resuelto vía `backend.read_active_profile(manifest_path)`; si retorna
    `None`, fallback al manifest path mismo (significa: el archivo no es
    manifest todavía, opera como hoy).
- **Nuevo método** `AppScreen.set_active_profile(new_profile_path: Path) -> None`
  con **orden transaccional**:
  1. `backend.write_active_profile(self.backend_manifest_path, new_profile_path)`.
     Si falla → propagar excepción / mostrar error toast; **no se toca
     state**.
  2. `self.backend_path = new_profile_path`. Solo después del write
     exitoso. A partir de acá, el manifest YA dice que el activo es el
     nuevo perfil — esa es la verdad lógica del switch.
  3. `reload_ok = backend.reload_after_profile_switch(self.backend_manifest_path, new_profile_path)`.
     **Best-effort**: si retorna `False` (Kitty IPC falla, instancia sin
     `listen_on`, etc.), mostrar warning toast con `manual_reload_hint`
     pero **mantener `self.backend_path` al nuevo perfil**.

  Fundamentación del orden: en v2, el manifest **es** el source of
  truth del switch. Una vez escrito, el switch lógico se consumó: la
  próxima ventana de terminal va a leer el nuevo perfil sí o sí. El
  reload es "aplicación al runtime de la ventana viva" y es
  intrínsecamente best-effort (en Alacritty no podemos esperar el
  watchdog; en Kitty el IPC puede fallar por estado transitorio sin
  invalidar el switch). Si tratáramos el reload como bloqueante de
  state, una falla IPC transitoria dejaría `self.backend_path`
  desincronizado con el manifest físico.

  Centraliza side effects (notify, posibles mensajes Textual a otras
  screens).
- Las screens reciben `backend_path` (perfil activo) por param como hoy,
  pero **no mutan `self.backend_path` directamente**. Para cambiar el
  activo (Load, Save-as con nombre nuevo), llaman a
  `self.app.set_active_profile(new)`.

### Fase D — Startup checks operan sobre el manifest (Kitty only)

`src/ztc/startup_checks.py`:

- Cambiar la firma de `build_kitty_remote_control_check` para que reciba
  `manifest_path` (no `backend_path` / perfil activo). Las directivas
  `allow_remote_control`, `listen_on`, `dynamic_background_opacity` y
  prefs `# ztc:` se leen y escriben en el manifest.
- Razón: esas directivas son globales para la instancia Kitty (no por
  perfil); si viven en un perfil intercambiable, cambiar de perfil
  rompe el remote control y deshabilita los reloads.
- Si el archivo aún no es manifest (no se hizo conversion), `manifest_path`
  = `default_config_path()` y todo opera como hoy.
- Alacritty no tiene startup checks → no aplica.

### Fase E — `action_load` (rename + nueva semántica + reload + dirty check)

En `screens/color_editor.py` y `screens/terminal_settings.py`:

1. Renombrar `action_import` → `action_load`. Cambiar binding `i` → `l`,
   label `"Import theme"` / `"Import"` → `"Load"`.
2. **Si `self.dirty=True`**: mostrar `UnsavedChangesModal` antes de
   proceder (mismo modal que `action_back`). Sin esto, Load pierde
   cambios silenciosamente.
3. Si no hay cambios pendientes o el user confirma descartar:
   - Resolver path (relativo a `manifest_path.parent` si no es absoluto).
   - **Si el default todavía no es manifest** (`not backend.is_managed_manifest(self.app.backend_manifest_path)`):
     disparar flow de conversión inicial (Fase G2) — mostrar el modal
     que pide el nombre para el perfil con los settings actuales del
     default, ejecutar `backend.convert_to_manifest(...)`. **Recién
     después** de que el manifest exista, continuar con el Load real.
     Si el user cancela el modal de conversión, abortar el Load.
   - **Cargar primero, asignar después** (orden transaccional, igual
     que `set_active_profile`): cargar el doc en una variable local,
     llamar a `set_active_profile`, y **recién después** actualizar el
     state local de la screen. Si `set_active_profile` lanza excepción
     (write del manifest falla), la screen queda mostrando lo viejo —
     no un perfil que no se aplicó.
     ```python
     new_doc = backend.load(path)
     self.app.set_active_profile(path)  # excepciona si write falla
     self.doc = new_doc
     self.backend_path = path
     self.dirty = False
     ```
   - Refrescar header, list, warnings.
4. Reordenar `BINDINGS`: `enter, x, r, l, s, esc`.

Notas:

- El comentario actual del `action_import` describe el comportamiento
  viejo; reescribir SIN referencia al cambio (regla del proyecto: "el
  código debe verse como si siempre hubiera sido así").
- `backend.import_theme_file` queda muerto después del rename. Verificar
  consumers; si solo lo usa `color_editor.py`, eliminar del protocol +
  implementaciones (cleanup al final).
- La detección + disparo del modal de conversión vive **en la screen**,
  no en `set_active_profile`. Razón: `set_active_profile` es método
  sync sin manejo de modals; pedir nombre al user requiere UI. La
  screen es el lugar natural.

### Fase F — `action_save` con modal de nombre + reglas explícitas

En `screens/color_editor.py` y `screens/terminal_settings.py`:

1. Abrir `PromptModal` con input prellenado (`self.backend_path.name`),
   `confirm_label="Save"`. Foco va al input por default (cumple "Enter
   directo guarda" sin cambios).
2. Validar el nombre antes de confirmar:
   - **Extensión esperada**: para Alacritty `.toml`, para Kitty `.conf`.
     Si no coincide, sugerir o rechazar (decisión: rechazar con error
     toast, fuerza al user a ser explícito).
   - **Path absoluto vs relativo**: relativo = relativo a
     `manifest_path.parent` (ya es el patrón en `action_import` hoy).
   - **Parent inexistente**: rechazar con error toast (no crear dirs
     automáticamente; minimiza efectos colaterales).
   - **Colisión con archivo existente**: si el archivo destino existe
     **y no es el `backend_path` actual**, mostrar `ConfirmModal`
     ("Sobrescribir X?"). Si es el mismo path actual: silencio (es save
     normal sobre el activo).
3. Si el nombre no cambió respecto al path actual (Save normal sobre
   el activo):
   - **Usar `save_profile_with_reload(backend, doc, backend_path, manifest_path)`**,
     no `save_with_reload`. Razón: el backend_path puede ser un perfil
     (`c64.conf`); `save_with_reload` mira el doc del perfil para
     decidir si hay que recargar, no encuentra las prefs runtime
     (`allow_remote_control`, `listen_on`) que viven en el manifest, y
     bailea con `return False`. `save_profile_with_reload` toma el
     manifest_path como segundo path para que el reload mire ahí. En
     Alacritty es transparente (no hay prefs runtime en el manifest).
4. Si el nombre cambió (Save-as a archivo nuevo):
   - **Si el default todavía no es manifest** (`not backend.is_managed_manifest(...)`):
     disparar flow de conversión inicial (Fase G2) primero. Si el user
     cancela, abortar el Save-as.
   - Escribir el archivo nuevo con `backend.save(doc, new_path)` (sin
     reload — el reload lo dispara `set_active_profile` después).
   - `self.app.set_active_profile(new_path)` ← propaga al app, escribe
     manifest para apuntar a `new_path`, dispara reload.
   - `self.backend_path = new_path`.
5. Refrescar header.

Notas:

- En el camino sin cambio de nombre (punto 3), `set_active_profile`
  **no se invoca**: el manifest ya apunta al activo, no hay switch
  lógico, solo edit del perfil.
- En el camino con cambio de nombre (punto 4), la separación
  `backend.save` + `set_active_profile` evita llamar a reload dos veces
  (una por `save_with_reload`, otra por `set_active_profile`).

### Fase G — Conversión inicial del default a manifest

Trigger: primera vez que Load o Save-as necesita
`write_active_profile()` y `is_managed_manifest(default)` retorna
`False`.

**Opciones a decidir**:

| | Comportamiento | Pros | Cons |
|---|---|---|---|
| **G1. Silencioso con backup** | ztc detecta no-manifest, hace backup `*.bak.<ts>`, mueve contenido a `default.toml` / `default.conf` (nombre fijo), reescribe el default como manifest. Toast informativo. | Cero fricción. | Decide nombre y momento sin avisar; el user no controla el primer perfil. |
| **G2. Modal explícito** *(recomendada)* | "Tu config actual se va a convertir a manifest. Nombre para el perfil con los settings actuales:" — input prellenado con `default`. Cancel / Confirm. Backup automático. | Control y visibilidad. | Un modal extra el primer uso. |
| **G3. Manual fuera de ztc** | Sin conversión automática. Si el user usa Load/Save-as sin manifest preparado, error con instrucciones doc. | Mínimo código. | Fricción alta. |

**Recomendación**: G2.

**Validaciones del modal G2** (mismas reglas que Save-as en Fase F,
aplicadas al nombre del primer perfil):

- **Extensión esperada**: `.toml` (Alacritty) / `.conf` (Kitty).
  Rechazar con error toast si no coincide.
- **Parent existente**: el nombre se resuelve relativo a
  `default_path.parent`. Si es un path con subdirs y el parent no
  existe, rechazar con error toast (no auto-crear).
- **No colisionar con el perfil que se está intentando cargar**: caso
  edge específico de G2 disparado desde Load. Si el user hace Load
  `c64.toml` y en el modal de conversión pone `c64.toml` como nombre
  del primer perfil, los dos paths colisionan antes de que el Load
  real arranque. Rechazar con error toast claro: "Ese nombre coincide
  con el perfil que estás cargando; elegí otro".
- **Confirmación si el archivo ya existe**: si el nombre apunta a un
  archivo existente (que no es el default), mostrar `ConfirmModal`
  ("Sobrescribir X?") antes de hacer el split.

**Pendiente**: confirmar el nombre default del primer perfil (sugerido:
`default.toml` / `default.conf`, pre-rellenado en el input).

### Fase H — Tests

Agregar/ajustar:

- **`test_terminal_alacritty.py`**: nuevos métodos
  (`read/write_active_profile`, `is_managed_manifest`,
  `convert_to_manifest`, `save_profile_with_reload`). Casos:
  - Archivo sin marcador (config standalone): `is_managed_manifest`
    devuelve `False`, `read_active_profile` devuelve `None`.
  - Archivo con marcador + un import: detectado, devuelve el path.
  - Marcador con múltiples imports: devolver el primero + warning toast.
  - Manifest inválido (marcador sin import): error explícito.
  - `convert_to_manifest`: contenido completo se mueve al perfil, default
    queda como manifest mínimo con marcador + import.
- **`test_terminal_kitty.py`**: idem para `include`. Reusar fixtures de
  includes existentes. Casos extra:
  - Existing `include theme.conf` SIN marcador → no tratado como
    manifest (test del bloqueante #2 del review original).
  - **`convert_to_manifest` Kitty hace split**: managed directives
    (`allow_remote_control`, `listen_on`, `dynamic_background_opacity`)
    y `# ztc:{...}` quedan en el manifest; colors/settings/resto del
    user (incluyendo includes propios) van al perfil. Verificar que un
    `# ztc:{"remote_control_pending_instance": "pid:N"}` previo se
    preserva en el manifest, no se mueve al perfil.
  - **`write_ztc_pref` supervivencia de `managed_manifest`**: cargar un
    doc con `# ztc:{"managed_manifest": true, "remote_control_modal": "dismissed"}`,
    llamar a `write_ztc_pref(doc, "remote_control_pending_instance", "pid:N")`,
    verificar que el JSON final contiene las tres keys (no solo las dos
    nuevas).
  - **`save_profile_with_reload` con manifest_path**: cargar un perfil
    Kitty (sin managed directives propias), llamar a
    `save_profile_with_reload(profile_doc, profile_path, manifest_path)`
    donde el manifest tiene `allow_remote_control yes` y `listen_on ...`.
    Verificar que el reload IPC se dispara (no baila con `return False`).
    Sin este pasaje del manifest, el bug del bloqueante #1 vuelve.
  - `reload_after_profile_switch`: dispara `load-config` y, si la
    opacity efectiva post-switch (calculada desde manifest + includes
    resueltos) es float, **siempre** dispara `set-background-opacity`
    con ese valor. Idempotente: si el valor no cambió respecto al
    estado vivo, el IPC no produce efecto visible. Si la opacity no
    está seteada o no parsea como float, solo `load-config`.
- **`test_color_editor_screen.py`** y **`test_terminal_settings_screen.py`**:
  nuevo flow de `action_load` (semántica, dirty check con modal,
  propagación al app), nuevo flow de `action_save` (modal, validación de
  extensión, colisión), bindings reordenados.
- **`test_app.py`** (nuevo o test de smoke ampliado):
  - init con manifest vs sin manifest.
  - **`set_active_profile` orden transaccional**:
    - Si `write_active_profile` falla (mock que lanza excepción):
      `self.backend_path` NO cambia + error toast.
    - Si `write_active_profile` OK + `reload_after_profile_switch`
      retorna `False` (mock): `self.backend_path` SÍ cambia al nuevo
      + warning toast con manual hint.
    - Camino feliz: state cambia + sin warning.
- **`test_startup_checks.py`** (nuevo o ampliar): Kitty check opera
  sobre `manifest_path`, no perfil.
- **`test_theme_sync.py`**:
  - `sync_terminal_with_zellij_theme` adoptó `save_profile_with_reload`
    (pasa el `manifest_path` cuando corresponde).
  - Cuando backend_path es perfil y manifest tiene remote control
    correctamente configurado, el reload IPC sí dispara (no bailea).

### Fase I — Doc (último paso)

Reescritura del showcase (`doc/C64_SHOWCASE.md`):

- Cambiar la filosofía: "modificá tu terminal" → "creá un perfil
  dedicado vía Load/Save". Las tablas de settings y colores se reusan
  como referencia.
- Sección nueva al final: cómo lanzar el perfil c64 desde un script
  externo (Alacritty con `--config-file ... -e zellij -n c64 -s main5`).
  Mencionar equivalentes Kitty/Ghostty sin comandos verificados.

Después: entrada en `doc/ROADMAP.md` para la versión correspondiente
(probablemente `v1.3.0`).

---

## Compatibilidad Alacritty vs Kitty

El patrón funciona para ambos pero la mecánica difiere. Resumen
comparativo:

| Aspecto | Alacritty | Kitty |
|---|---|---|
| **Formato manifest** | `[general] import = ["c64.toml"]` | `include c64.conf` |
| **Marcador ztc** | Sección TOML `[ztc] managed_manifest = true` | Clave `managed_manifest` dentro del JSON `# ztc:{...}` existente (convive con prefs runtime como `remote_control_pending_instance`) |
| **Live-reload de la terminal** | Nativo: watchdog re-lee el archivo default y sigue imports automáticamente | NO nativo: requiere `kitty @ load-config` vía IPC |
| **Costo de `set_active_profile`** | Solo `write_active_profile` (escribir manifest); el reload es pasivo | `write_active_profile` + `kitty @ load-config` + posible `set-background-opacity` |
| **Caveat opacity** | N/A | Sí: cambio de perfil puede mover opacity sin que `doc.changed_settings` lo marque. Resolución: `reload_after_profile_switch` dispara `set-background-opacity` siempre que la opacity efectiva post-switch sea float (idempotente — sin efecto si el valor coincide con el estado vivo). |
| **Startup checks** | Ninguno (no requiere remote control) | Sí (`allow_remote_control`, `listen_on`, `dynamic_background_opacity`, prefs `# ztc:`). **Deben escribir al manifest, no al perfil** |
| **Pre-requisito para reload** | Ninguno | Remote control configurado (cubierto por startup checks ya existentes) |
| **Backend hoy** | Sin infra de imports | Con infra de includes (`_MAX_INCLUDE_DEPTH=5`, etc.) — adaptable |
| **Trabajo neto** | Implementar 4 métodos nuevos en el backend | Implementar 4 métodos + `reload_after_profile_switch` + adaptar startup_checks |

**Conclusión**: Alacritty es la implementación más simple (live-reload
hace casi todo). Kitty requiere más mecánica (reload explícito + opacity
+ startup checks al manifest), pero todo es factible y se apoya en infra
existente. **Ambos terminan con la misma experiencia user-facing**: Load
cambia el perfil activo y la terminal aplica en vivo.

---

## Puntos donde mantengo criterio sobre la review (con fundamentación)

La review fue de calidad y acepté 8/8 observaciones como válidas. En
tres puntos mantengo matices propios sobre la implementación, no sobre
el hallazgo. Listo el detalle:

### 1. Propagación de cambios al app state: setter explícito vs mutación directa

**Propuesta de la review**: "Load/Save-as actualicen también
`self.app.backend_path`" (mutación directa desde la screen).

**Mi criterio**: exponer un método `AppScreen.set_active_profile(path)`
que las screens llaman; el método encapsula la mutación + el efecto
secundario (`write_active_profile` + reload + notificaciones).

**Fundamentación técnica**:

- **Pattern actual del proyecto**: las screens usan `self.app.notify(...)`,
  `self.app.push_screen(...)`, `self.app.pop_screen()` — invocan
  métodos del app, no mutan atributos suyos. Mantener consistencia con
  el patrón existente.
- **Encapsulamiento**: el switch de perfil **no es solo "cambiar un
  path"**. Implica tres efectos coordinados: actualizar el path en
  memoria, escribir el manifest a disco, disparar el reload de la
  terminal (especialmente Kitty). Si cada caller (Load, Save-as)
  reimplementa los tres pasos, hay riesgo de divergencia. Si lo hace
  `set_active_profile`, queda centralizado.
- **Side effects centralizados**: mañana puede sumarse "notificar a
  otras screens abiertas via mensaje Textual" o "persistir el activo en
  disco entre sesiones de ztc". Si está encapsulado en un setter, esos
  agregados son no-invasivos.
- **Testabilidad**: testear `set_active_profile` una sola vez cubre los
  invariantes; testear cada caller por separado tiene más superficie.

### 2. Detección de manifest gestionado: marcador explícito + sin fallback heurístico

**Propuesta de la review**: "detectar solo manifests administrados por
ztc, idealmente con marcador propio, **o como mínimo 'manifest puro'**:
comentarios + una sola referencia activa + sin settings directos".

**Mi criterio**: marcador propio obligatorio. Sin fallback heurístico de
"manifest puro".

**Fundamentación técnica**:

- **La heurística "manifest puro" es ambigua y frágil**. Un archivo con
  solo `import = ["theme.toml"]` puede ser:
  (a) Un manifest legítimo creado por ztc.
  (b) Una config minimalista que el user escribió a mano para cargar un
      tema sin tener settings propios.
  Si ztc trata (b) como gestionado, va a editar `theme.toml` y el user
  pierde la separación que él diseñó.
- **El marcador resuelve la ambigüedad sin falso positivo**. Si está,
  fue ztc. Si no, no.
- **Precedente en el repo**: Kitty backend ya usa `# ztc:<json>` para
  preferences (`_ZTC_PREF_RE` en `kitty.py:97`). El patrón está
  validado. Para Alacritty creamos el equivalente (`[ztc]` sección
  TOML).
- **Para el caso del user que ya tiene "manifest puro" sin marcador**:
  la Fase G (conversión inicial con modal) cubre adoptarlo —
  explícito, controlado, con su consentimiento.

### 3. Save-as edge cases: defaults razonables, no un mega-modal de validación

**Propuesta de la review**: "Save-as necesita reglas claras: extensión
esperada, colisión con archivo existente, rutas relativas, parent
inexistente."

**Mi criterio**: defaults razonables y rechazo simple para edge cases,
no UI de validación compleja.

**Fundamentación técnica** (las 4 decisiones en Fase F arriba):

- **Extensión**: rechazar con error toast si no coincide (`.toml` para
  Alacritty, `.conf` para Kitty). Razón: aceptar extensiones random
  arrastra problemas downstream (terminal no lee, sintaxis ambigua).
  Mejor fricción explícita.
- **Parent inexistente**: rechazar sin auto-crear. Razón: crear dirs
  silenciosamente puede ensuciar `~/.config` con paths typo. El user
  tipea `~/.config/c64.toml` queriendo decir `~/.config/alacritty/c64.toml`
  → con auto-create tendrías un archivo en el lugar equivocado y sin
  enterarte.
- **Colisión solo si destino ≠ activo**: si guardás "sobre" el archivo
  que ya estás editando, es save normal (no preguntar). Si es otro
  archivo que existe, preguntar (`ConfirmModal` que ya está en
  `widgets/confirm.py`).
- **Relativos**: usar `manifest_path.parent` como base (consistente con
  `action_import` actual, no inventar nuevo patrón).

Estas reglas se implementan con código simple — un `if` por edge case
en el handler del modal, no un mega-validador.

---

## Riesgos identificados

1. **Cambio de semántica de Import**: si algún usuario actual usa el
   merge para algo (`import_theme_file`), lo pierde tras el rename.
   Mitigación: el feature es reciente (Kitty parity v1.2.0); documentar
   en release notes.
2. **Conversión inicial es invasiva**: el archivo `alacritty.toml` /
   `kitty.conf` pierde standalone-ness. Mitigación: Fase G2 (modal
   explícito) + backup automático.
3. **`read_active_profile` con múltiples imports**: si un manifest
   gestionado por ztc tiene más de un import/include (no debería pasar
   normalmente), tomar el primero + warning toast.
4. **`kitty @ load-config` y re-evaluación de includes**: el plan asume
   que load-config re-evalúa includes. **Verificar en runtime al
   arrancar Fase B** antes de cerrar esa fase. Plan B: si load-config
   no basta, cargar el include explícitamente.
5. **Profile-switch + opacity sin `changed_settings`**: cubierto por
   `reload_after_profile_switch` disparando `set-background-opacity`
   siempre que la opacity efectiva post-switch sea float (idempotente
   — Fase B).

---

## Archivos tocados (estimado)

- `src/ztc/services/terminals/__init__.py` (protocol)
- `src/ztc/services/terminals/alacritty.py` (imports support)
- `src/ztc/services/terminals/kitty.py` (active include + reload_after_profile_switch)
- `src/ztc/app.py` (manifest_path + active backend_path + set_active_profile)
- `src/ztc/startup_checks.py` (operar sobre manifest, no perfil)
- `src/ztc/screens/color_editor.py` (Load + Save modal + bindings + dirty check)
- `src/ztc/screens/terminal_settings.py` (idem)
- `tests/test_terminal_alacritty.py`
- `tests/test_terminal_kitty.py`
- `tests/test_color_editor_screen.py`
- `tests/test_terminal_settings_screen.py`
- `tests/test_app.py` (o smoke ampliado)
- `tests/test_startup_checks.py` (nuevo o ampliar)
- `tests/test_theme_sync.py`
- `doc/C64_SHOWCASE.md`
- `doc/ROADMAP.md`

Total: ~15–16 archivos.

## Estrategia de commits

Un commit por fase (A, B, C, D, E, F+G, H, I). Cada uno deja el repo en
estado coherente (tests pasando). La Fase A se commitea sin uso real
todavía (el protocol crece pero las screens no llaman a los métodos
nuevos hasta E/F).

Branching: `feat/terminal-profiles-manifest` (o similar). Plan v2
aprobado va commiteado a `main` antes de empezar la ejecución, como
manda la regla "Bloques documentales aprobados" de `agent-behavior.md`.
