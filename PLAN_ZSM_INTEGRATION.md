# Plan: integracion opcional de zsm en ztc

## Contexto y motivacion

### Workflow real del usuario

`zsm` se concibio como **terminal launcher pre-Zellij**. Cada vez que se abre una terminal nueva, el usuario invoca `zsm` desde el shell para decidir como entrar:

- attach a una sesion Zellij existente (running/exited),
- crear una sesion nueva (con o sin layout),
- caer en `bash` sin Zellij.

Es un launcher rapido, no una app de configuracion.

`ztc` es la app de configuracion (temas Zellij, layouts, colores de terminal). Vive en otro plano: el usuario la abre cuando quiere editar config, no cuando quiere lanzar una terminal.

### Problema tecnico que motivo separar zsm de ztc

Originalmente `zsm` y `ztc` estaban juntos. Se separaron porque algunas operaciones de gestion de sesiones (attach a otra, crear nueva) **fallan si se ejecutan desde dentro de Zellij** — la rama no se puede cortar desde si misma. Tener todo dentro de un editor de config que se abria *desde dentro de Zellij* rompia esos flujos.

Con `zsm` standalone como launcher pre-Zellij, el problema desaparecio: `zsm` siempre se ejecuta antes de entrar a una sesion, no desde dentro.

### Por que ahora se puede integrar

Caso de uso primario: **ni `zsm` ni `ztc` se invocan desde dentro de Zellij**. Cuando el usuario corre `zsm` o `ztc`, o no hay Zellij activo, o las sesiones existentes estan en estado `exited` / `detached` y la terminal donde corre la app no es uno de sus panes.

En ese caso primario, todas las operaciones de `zsm` (attach, new, kill, delete, rename) son seguras desde `ztc` con el patron actual de `os.execvp`. **El bloqueo "cortar la rama desde la rama" no aplica.**

Caso secundario: **`ztc` puede correr dentro de Zellij**. Eso es valido para themes/layouts/terminal-colors (no tienen ninguna restriccion). Para el item Sessions hay un subset de operaciones que Zellij rechaza si se invocan desde dentro de una sesion (attach a otra, crear nueva) o que serian suicidio (kill/delete de la sesion actual). El plan contempla este caso con gating selectivo (Fase 4).

### Que se quiere lograr

Que `ztc` muestre un item "Zellij sessions" en su menu principal **si detecta que `zsm` esta instalado en el mismo entorno Python**. Ese item monta la `PickerScreen` de `zsm` como sub-screen de `ztc`.

`zsm` sigue **intacto como CLI standalone**. Es el launcher principal y el caso de uso primario. La integracion en `ztc` es secundaria: comodidad cuando el usuario ya esta editando config y quiere atachar/crear sin volver al shell.

### Lo que NO se va a hacer (fuera de scope, descartado en discusion)

- **Embeber `zsm` como otra App Textual dentro de `ztc`**: Textual no permite anidar `App`. Una sola `App` controla el TTY.
- **`subprocess + suspend()`**: visualmente no se ve integrado y agrega complejidad sin ganancia.
- **Flag `ztc --sessions`** que arranque directo en `PickerScreen`: el launcher rapido es `zsm` directo. Tener dos comandos para lo mismo es ruido.
- **Deprecar `zsm`**: el caso de uso "launcher liviano sin tocar config" sigue siendo valido para usuarios que no quieren todo el paquete de `ztc`.

## Decisiones de diseno

### 1. Acoplamiento minimo via soft-import

`ztc` **no** declara `zsm` como dependencia obligatoria. Lo importa con `try/except` y degrada elegantemente si no esta disponible:

```python
try:
    from zsm.screens.picker import PickerScreen
    HAS_ZSM = True
except ImportError:
    HAS_ZSM = False
```

### 2. `[project.optional-dependencies]` para activar la integracion

En `ztc/pyproject.toml`:

```toml
[project.optional-dependencies]
sessions = ["zsm"]
```

El usuario activa la integracion con `uv tool install "ztc[sessions]"` (o equivalente). Sin ese extra, `ztc` funciona normal y el item "Sessions" no aparece.

### 3. Refactor de `PickerScreen` para desacoplarla de `ZsmApp`

`PickerScreen` actualmente toca `self.app.target` directamente:

- `screens/picker.py:407, 408` → attach: `app.target = ("attach", ...); app.exit()`
- `screens/picker.py:411, 412` → bash: `app.target = ("bash", ...); app.exit()`
- `screens/picker.py:451, 452` → new: `app.target = ("new", ...); app.exit()`
- `screens/picker.py:575, 576` → quit/cancel: `app.target = None; app.exit()`

Eso la acopla a `ZsmApp` que tiene ese atributo, y mezcla **dos responsabilidades distintas**: lanzar un target externo (los primeros 3 casos) y cancelar/cerrar la pantalla (el 4to). Cuando `PickerScreen` se monta como sub-screen de `ztc`, el `app.exit()` del cancel cerraría toda la app, no solo la pantalla.

Hay que **inyectar dos callbacks separados**:

```python
class PickerScreen(Screen[None]):
    def __init__(
        self,
        *,
        on_launch: Callable[[LaunchTarget], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._on_launch = on_launch or self._default_launch
        self._on_cancel = on_cancel or self._default_cancel

    def _default_launch(self, target: LaunchTarget) -> None:
        # Comportamiento standalone: setear app.target + exit.
        self.app.target = target  # type: ignore[attr-defined]
        self.app.exit()

    def _default_cancel(self) -> None:
        # Comportamiento standalone: target=None + exit.
        self.app.target = None  # type: ignore[attr-defined]
        self.app.exit()
```

`ZsmApp` sigue funcionando igual (no pasa callbacks → usa defaults). `ztc` pasa:

- `on_launch` que hace `os.execvp` directamente (sin necesidad de tener un atributo `target`).
- `on_cancel` que hace `self.app.pop_screen()` para volver al menu de `ztc`.

### 4. `ztc` no corre dentro de Zellij — `os.execvp` directo

Cuando el usuario hace attach/new desde el item Sessions en `ztc`, `ztc` ejecuta `os.execvp` igual que `zsm` standalone:
- `ztc` termina,
- el proceso se reemplaza por `zellij attach NAME` (o equivalente),
- al cerrar Zellij, el shell vuelve.

No se usa `App.suspend() + subprocess.run`. Es consistente con `zsm` y simple.

## Pasos de ejecucion

### Fase 1: Refactor de `zsm` (PickerScreen reusable)

Repo: `/home/martin/Documents/zsm`

1. **Nuevo `src/zsm/types.py`**: extraer `LaunchTarget` a este modulo:
   ```python
   LaunchTarget = tuple[str, str | None, str | None] | None
   ```
   `zsm/app.py:13` actualmente define ese tipo y `zsm/app.py:9` ya importa `PickerScreen` desde `zsm.screens.picker`. Si dejaramos `LaunchTarget` en `zsm/app.py` y `picker.py` lo importara desde alli, **import circular garantizado**. Por eso va a un modulo nuevo sin dependencias.
   - Actualizar `zsm/app.py` para importar `LaunchTarget` desde `zsm.types`.

2. **`src/zsm/screens/picker.py`**: agregar parametros `on_launch` y `on_cancel` en `__init__`, con fallback al comportamiento standalone actual.
   - Importar `LaunchTarget` desde `zsm.types`.
   - Reemplazar las 3 ocurrencias de launch (`self.app.target = X; self.app.exit()` con X != None — lineas 407-408, 411-412, 451-452) por `self._on_launch(X)`.
   - Reemplazar la ocurrencia de cancel (`self.app.target = None; self.app.exit()` — lineas 575-576) por `self._on_cancel()`.

3. **`src/zsm/__init__.py`**: re-exportar API publica para que `from zsm import PickerScreen, LaunchTarget, attach_argv, new_session_argv` funcione:
   ```python
   from zsm.screens.picker import PickerScreen
   from zsm.services.zellij_session import attach_argv, new_session_argv
   from zsm.types import LaunchTarget

   __all__ = ["PickerScreen", "LaunchTarget", "attach_argv", "new_session_argv"]
   ```
   Exportar `attach_argv` / `new_session_argv` (ya existen en `services/zellij_session.py:294, 299`) es **obligatorio** — la regla de DRY oportunista del proyecto exige consolidar la construccion de argv en un unico lugar antes de cerrar el refactor; permitir que `ztc` los duplique seria fabricar deuda nueva durante un refactor que pretende limpiar.

4. **Tests**: 45/45 deben seguir pasando. Los tests existentes usan el comportamiento default (sin callbacks), asi que los fallbacks los cubren.

5. **Commit**: `refactor: PickerScreen acepta callbacks on_launch/on_cancel para reuso desde otras apps`.

### Fase 2: Integracion en `ztc`

Repo: `/home/martin/Documents/ztc`

1. **`pyproject.toml`**:
   ```toml
   [project.optional-dependencies]
   sessions = ["zsm"]
   ```
   Para desarrollo local con uv, agregar tambien path source:
   ```toml
   [tool.uv.sources]
   zsm = { path = "../zsm", editable = true }
   ```

2. **`src/ztc/app.py`**:
   - Soft-import al tope del modulo, importando los helpers publicos:
     ```python
     try:
         from zsm import PickerScreen, attach_argv, new_session_argv
         HAS_ZSM = True
     except ImportError:
         PickerScreen = None  # type: ignore[assignment]
         attach_argv = None  # type: ignore[assignment]
         new_session_argv = None  # type: ignore[assignment]
         HAS_ZSM = False
     ```
   - `_build_menu_options()`: si `HAS_ZSM`, agregar `Option(f"Zellij sessions{zellij_suffix}", id="sessions", disabled=zellij_disabled)` **inmediatamente despues de "Zellij layouts"**, antes de "Terminal colors". Reusa el `zellij_suffix` y `zellij_disabled` ya calculados (`app.py:153-154`) — mismo patron que los items existentes. Orden final del menu con `HAS_ZSM=True`: `Zellij theme` → `Zellij layouts` → `Zellij sessions` → `Terminal colors`.
   - Si `HAS_ZSM=True` pero `zellij_installed=False`: el item aparece disabled con suffix `(zellij not installed)`, igual que Zellij theme/layouts. No se oculta — el usuario ve que la feature existe pero requiere zellij.
   - `_on_menu_selected()`: nuevo branch para `event.option.id == "sessions"` que monta `PickerScreen` con `on_launch=self._handle_session_launch` y `on_cancel=lambda: self.pop_screen()`.
   - Nuevo metodo `_handle_session_launch(target)` que **usa los helpers publicos importados de `zsm`** (sin duplicar argv):
     ```python
     def _handle_session_launch(self, target):
         action, payload, extra = target
         if action == "attach":
             argv = attach_argv(payload)
         elif action == "new":
             argv = new_session_argv(payload, layout=extra)
         elif action == "bash":
             shell = os.environ.get("SHELL") or "/bin/bash"
             argv = [shell]
         else:
             return
         os.execvp(argv[0], argv)
     ```
     (`target=None` ya no llega aqui — el cancel va por `on_cancel` separado, ver Decision §3.)

3. **Width del menu**: el item "Sessions" extiende el ancho minimo del menu. Verificar que `width: 25` sigue alcanzando o ajustar.

4. **Tests**:
   - 206 existentes deben seguir verdes.
   - Agregar tests:
     - Si `zsm` esta instalado, el menu tiene 4 items; si no, 3.
     - El item Sessions aparece con suffix `(zellij not installed)` y disabled cuando `zellij_installed=False`.
     - `q/Esc` desde `PickerScreen` embebido vuelve al menu de ztc (no cierra la app).
     - `attach/new/bash` invocan `os.execvp` con argv esperado (monkeypatchear `os.execvp` y `attach_argv` / `new_session_argv`).
   - Para mockear `HAS_ZSM` en tests: `monkeypatch.setattr("ztc.app.HAS_ZSM", False)`. **Importante**: el patch debe aplicarse **antes de instanciar la app** (`app = TermConfigApp(); async with app.run_test(): ...`), porque `_build_menu_options()` se llama en `compose()` durante el mount y consulta `HAS_ZSM` en ese momento. Patcharlo despues de `run_test()` no surte efecto: el menu ya esta armado. No requiere refactor del flag a funcion/lazy import.

5. **Commit**: `feat: integrar PickerScreen de zsm como item opcional en menu`.

### Fase 3: Verificacion manual (caso primario, fuera de Zellij)

1. **Sin zsm instalado**: `ztc` muestra solo los 3 items originales. No falla, no rompe.
2. **Con zsm instalado**: `ztc` muestra "Sessions" como cuarto item. Al seleccionarlo monta PickerScreen.
3. **Desde PickerScreen → attach/new/bash**: `ztc` termina, proceso se convierte en zellij/bash. Comportamiento identico a `zsm` standalone.
4. **Desde PickerScreen → Esc/q**: vuelve al menu de `ztc`.
5. **`zsm` standalone sigue funcionando**: invocar `zsm` desde el shell debe seguir comportandose igual que ahora.

### Fase 4 (iteracion 2): Gating cuando `ztc` corre dentro de Zellij

> **Estado: NO implementar junto con Fases 1-3.** Fase 4 requiere validacion empirica previa de la semantica real de Zellij (que operaciones funcionan desde dentro y cuales no — `zellij --help` v0.44.1 ya muestra que `-n` "Will always start a new session, even if inside an existing session", contradiciendo la matriz original). Implementar bindings/toasts sin haber probado cada caso seria fabricar falsos positivos como los que ya eliminamos en `compute_warnings`.

Soporta el caso secundario: `ztc` invocado desde un pane de Zellij. Themes/layouts/terminal-colors no requieren ningun cambio. El item Sessions habilita un subset de operaciones segun contexto.

#### Paso previo: validacion empirica de la semantica real de Zellij

Antes de redactar la implementacion final, ejecutar manualmente cada operacion desde dentro de una sesion Zellij `A` y registrar el comportamiento real (exit code, mensaje de error, side effects observables):

| Comando | Esperado segun manual / asuncion | Validar |
|---|---|---|
| `zellij` (sin args) | Atacha a la sesion actual o falla | ¿Cual? |
| `zellij attach OTRA` | Falla "Can't connect from within a session" (asumido) | Confirmar |
| `zellij -s NUEVA` | Comportamiento dudoso | Probar |
| `zellij -n LAYOUT -s NUEVA` | Crea nueva sesion (manual lo dice explicito) | Confirmar |
| `zellij kill-session OTRA` | OK (no toca la actual) | Confirmar |
| `zellij delete-session OTRA` (exited) | OK | Confirmar |
| `zellij action rename-session NEW` | OK (renombra la actual) | Confirmar |
| `zellij --session OTRA action rename-session NEW` | OK (renombra otra) | Confirmar |

El resultado de esta validacion **redefine la matriz** y la lista de operaciones bloqueadas. Sin este paso, la matriz de abajo es especulativa.

#### Deteccion

```python
ZELLIJ_ACTIVE = bool(os.environ.get("ZELLIJ"))
CURRENT_SESSION = os.environ.get("ZELLIJ_SESSION_NAME")
```

Zellij setea ambos automaticamente en cada pane. Si `ZELLIJ` esta presente, `ztc` corre dentro de una sesion; `ZELLIJ_SESSION_NAME` identifica cual.

#### Matriz especulativa (revalidar tras paso previo)

Asumiendo `ztc` dentro de la sesion `A`. Esta matriz refleja la asuncion previa al manual de Zellij; **el paso previo puede mover varios casos de "bloqueado" a "permitido"**.

| Accion | Sobre sesion `A` (actual) | Sobre sesion `B` (otra) |
|---|---|---|
| Attach | Sin sentido (ya estas ahi) — bloquear | Zellij rechaza (a confirmar) — bloquear + toast |
| Kill | Suicidio del pane que corre `ztc` — bloquear + toast | OK |
| Delete (exited) | N/A (la actual esta running) | OK |
| Rename | OK | OK |
| New con layout (`-n -s`) | Manual dice "always start a new session" — **probablemente OK** | — |
| New sin layout (`-s`) | A confirmar empiricamente | — |
| Bash (b) | Tecnicamente posible pero raro desde adentro — bloquear + toast | — |

#### Implementacion en `PickerScreen` (zsm)

> **Nota tecnica importante**: `Binding` de Textual **no tiene parametro `disabled`** (verificado en runtime: los fields del dataclass son `[key, action, description, show, key_display, priority, tooltip, id, system, group]`). El gating no se hace via `Binding(disabled=True)`. Las dos opciones validas:
>
> - **Construir `BINDINGS` dinamicamente** en `__init__` o `on_mount`: incluir solo los bindings aplicables al contexto, omitiendo (o marcando `show=False`) los bloqueados.
> - **Guards en los handlers**: el binding sigue registrado, pero el `action_*` correspondiente verifica el contexto y muestra toast + return temprano si esta bloqueado.
>
> El combo recomendado es: **omitir del Footer** los bindings bloqueados (mas claro visualmente — el usuario no los ve como opcion) **+ guard en handler** (red de seguridad por si el evento se dispara igual).

`PickerScreen` debe aceptar un parametro de contexto `inside_zellij_session: str | None` con la sesion actual (None si esta fuera). Con eso:

- Construccion dinamica de `BINDINGS`: si `inside_zellij_session is not None`, omitir los bindings cuyas operaciones esten bloqueadas segun la matriz validada en el paso previo.
- Guards en handlers de attach / kill / delete-force: si target == sesion actual o si la operacion esta bloqueada por contexto, mostrar toast explicativo y `return`.
- Rename y delete-exited (sobre otras): sin cambios.

#### Implementacion en `ztc`

Cuando `ztc` instancia `PickerScreen`, le pasa el contexto. Dentro de `TermConfigApp` se usa `self.push_screen(...)` (no `self.app.push_screen(...)` — `self` ya es la app):

```python
self.push_screen(
    PickerScreen(
        on_launch=self._handle_session_launch,
        on_cancel=lambda: self.pop_screen(),
        inside_zellij_session=os.environ.get("ZELLIJ_SESSION_NAME") if os.environ.get("ZELLIJ") else None,
    )
)
```

#### Compat con `zsm` standalone

`ZsmApp` tambien deberia hacer la deteccion (caso raro: usuario invoca `zsm` desde dentro de Zellij). Hoy `zsm` no lo hace y simplemente fallaria al `execvp` si intenta operaciones bloqueadas — el toast/omision mejora la UX universalmente. Aplicar la misma deteccion en `ZsmApp.on_mount()` y pasarla a `PickerScreen`.

#### Verificacion manual (caso secundario)

1. Lanzar `ztc` desde dentro de Zellij sesion `A` (con sesion `B` exited y sesion `C` running en otra terminal).
2. Item "Sessions" aparece como antes.
3. Los bindings bloqueados (segun matriz validada) no aparecen en el Footer o aparecen `show=False`.
4. En el listado: `A` marcada como "current" (algun indicador visual). Las operaciones bloqueadas sobre `A` muestran toast bloqueante.
5. Las operaciones permitidas sobre `B` y `C` funcionan.
6. Rename funciona en todas.

## Riesgos y consideraciones

### `zsm` como dependencia path en uv

Para desarrollo local funciona con `[tool.uv.sources]` apuntando a `../zsm`. Pero si en el futuro se publica `ztc` a PyPI, esa source debe sacarse o reemplazarse por un release de `zsm`. **No bloqueante hoy** (uso local), pero anotar para cuando se publique.

### Tests de integracion

Los tests de `ztc` no deben requerir `zsm` instalado. Usar `pytest.importorskip("zsm")` en los tests que dependen del item Sessions, o mockear `HAS_ZSM`.

### `ZsmApp.target` sigue siendo el contrato standalone

Despues del refactor de Fase 1, `ZsmApp` debe seguir funcionando igual: ejecutar `zsm` desde el shell sigue setteando `app.target` y haciendo `execvp` desde `__main__.py`. El callback es solo para clientes externos (ztc).

## Que dejamos sin tocar

- `zsm` standalone CLI: sin cambios funcionales, solo el refactor de callback con default backwards-compatible.
- `zellij-themes` (paquete shared): sin cambios.
- Tests existentes: los 206 de ztc + 45 de zsm + 8 de zellij-themes deben seguir verdes.

## Resumen ejecutivo

| | Antes | Despues Fases 1-3 (MVP) | Despues Fase 4 (iter. 2) |
|---|---|---|---|
| `zsm` standalone | Launcher pre-Zellij funcional | Igual, sin cambios funcionales | + gating si se invoca dentro de Zellij |
| `ztc` solo | 3 items en menu | 3 items en menu | 3 items en menu |
| `ztc[sessions]` | No existia | 4 items: + "Zellij sessions" (despues de "Zellij layouts") que monta PickerScreen (sin gating contextual; asume fuera de Zellij) | 4 items con gating contextual del item Sessions cuando ztc corre dentro de Zellij |
| Acoplamiento `ztc → zsm` | N/A | Soft-import opcional, falla limpia si zsm no esta | (igual) |
| Codigo duplicado | N/A | Cero (ztc importa helpers de zsm) | (igual) |
| Caso `ztc` dentro de Zellij | N/A (hoy ztc no integra zsm) | Themes/layouts/colors sin restriccion; Sessions funciona pero sin gating (operaciones bloqueadas por Zellij fallan ruidosamente) | Sessions con subset habilitado segun matriz validada empiricamente |
