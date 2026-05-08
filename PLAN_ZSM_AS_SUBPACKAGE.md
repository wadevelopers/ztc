# Plan: zsm como subpaquete de ztc (consolidacion)

> **Plan alternativo a [`PLAN_ZSM_INTEGRATION.md`](PLAN_ZSM_INTEGRATION.md).** Aquel plan trata zsm y ztc como paquetes pip separados con integracion via `[project.optional-dependencies]` y soft-import. Este plan los consolida en un unico paquete (`ztc`) con dos CLIs (`ztc` y `zsm`). El plan anterior queda intacto como referencia historica de la decision; este es el camino a ejecutar.

## Contexto y motivacion

### Workflow real del usuario

`zsm` se concibio como **terminal launcher pre-Zellij**. Cada vez que se abre una terminal nueva, el usuario invoca `zsm` desde el shell para decidir como entrar:

- attach a una sesion Zellij existente (running/exited),
- crear una sesion nueva (con o sin layout),
- caer en `bash` sin Zellij.

Es un launcher rapido, no una app de configuracion.

`ztc` es la app de configuracion (temas Zellij, layouts, colores de terminal). Vive en otro plano: el usuario la abre cuando quiere editar config, no cuando quiere lanzar una terminal.

### Por que ahora se consolida

Despues de discusion, quedo claro que conceptualmente:

- `ztc` es la app "completa" / contenedor de features.
- `zsm` es **una feature de ztc** que ademas tiene su propio comando rapido de invocacion para no obligar al usuario a navegar el menu.
- Futuras features (otros "lanzadores" / pantallas especializadas) seguirian el mismo patron: subpaquetes dentro de ztc con su propio CLI si el caso lo justifica.

Esa semantica **no es** la de dos paquetes pip independientes con integracion opcional. Es la de **un paquete con multiples CLIs**.

### Alternativas descartadas

| Opcion | Por que se descarta |
|---|---|
| α — Dos paquetes pip + `[project.optional-dependencies] sessions = ["zsm"]` con soft-import (plan original) | `uv tool install` aisla por tool. Para tener ambos CLIs en PATH (`ztc` y `zsm`) hacen falta dos `uv tool install` separados, con duplicacion de `zellij-themes` en disco. La integracion no es automatica: el usuario tiene que recordar el comando con el extra (`uv tool install "ztc[sessions]"`) o usar `--with`. UX confuso para algo que conceptualmente es una sola app. |
| β — Plugin architecture con entry points | Sigue requiriendo mismo venv. Sigue sin resolver `zsm` standalone con `uv tool` (los entry points no exponen scripts de deps). Infraestructura grande para una sola feature: YAGNI hasta tener el segundo plugin real. |
| γ — **Consolidar zsm como subpaquete de ztc** (este plan) | Un solo paquete pip. `uv tool install ztc` expone los dos CLIs gratis. Integracion automatica (import directo). Cero packaging hackery. Extensible: agregar un tercer CLI es agregar un subpaquete + un script en `[project.scripts]`. |

### Que se quiere lograr

1. **Un solo paquete pip**: `ztc` (en su `pyproject.toml`).
2. **Dos comandos CLI**: `ztc` (UI completa) y `zsm` (launcher de sesiones, lanza directo a `PickerScreen`).
3. **Instalacion trivial**: `uv tool install ztc` deja ambos CLIs en PATH automaticamente.
4. **Integracion siempre activa**: el item "Zellij sessions" del menu de ztc esta siempre disponible (gateado solo por `zellij_installed`, igual que los otros items de Zellij).
5. **Repo `zsm` independiente se archiva**: el codigo vive dentro de `ztc/src/ztc/sessions/`. El repo `/home/martin/Documents/zsm` queda archivado / en read-only, no se publica nuevas versiones.
6. **Reorganizacion de docs**: todos los planes/notes a `doc/`. Solo `README.md` queda en la raiz como punto de entrada al proyecto.

### Lo que NO se va a hacer (fuera de scope)

- **Plugin architecture genericha** (entry points, descubrimiento dinamico): YAGNI. Se evalua si aparece un tercer subcomando con perfil similar.
- **Preservar git history de zsm** (con `git subtree` o `git filter-repo`): opcional. Si el usuario quiere puede ejecutarse, pero no es requisito del plan.
- **Embeber `zsm` como otra App Textual dentro de `ztc`** (la opcion C que descartamos hace varias iteraciones): sigue sin aplicar. Textual no permite anidar Apps.
- **Gating dentro de Zellij** (la Fase 4 del plan original): se mantiene como **iteracion posterior**, con la misma validacion empirica que ya estaba prevista. Este plan deja la base lista para implementarla (PickerScreen acepta el contexto), pero no la implementa aun.

## Decisiones de diseno

### 1. Estructura final del paquete `ztc`

```
ztc/
├── pyproject.toml              ← declara dos scripts (ztc, zsm)
├── README.md                   ← punto de entrada con seccion Installation
├── .gitignore                  ← + reglas para evitar planes en raiz por accidente
├── doc/
│   ├── PLAN_ZSM_INTEGRATION.md         (historico, plan α descartado)
│   ├── PLAN_ZSM_AS_SUBPACKAGE.md       (este)
│   ├── PLAN_MULTI_TERMINAL.md          (existente)
│   ├── PLAN_TUI_FROM_ALACRITTY.md      (existente)
│   ├── PLAN.md                         (existente)
│   └── NOTES.md                        (existente)
├── src/
│   └── ztc/
│       ├── __init__.py
│       ├── __main__.py                 (entry point del CLI `ztc`)
│       ├── app.py
│       ├── models/
│       ├── screens/
│       ├── services/
│       ├── widgets/
│       └── sessions/                   ← antes era el paquete `zsm` independiente
│           ├── __init__.py
│           ├── __main__.py             (entry point del CLI `zsm`)
│           ├── app.py                  (SessionLauncherApp wrapper standalone)
│           ├── types.py                (LaunchTarget)
│           ├── models/
│           ├── screens/
│           │   └── picker.py           (PickerScreen con on_cancel callback)
│           ├── services/
│           └── widgets/
└── tests/
    ├── (208 tests existentes de ztc)
    └── sessions/                       ← antes era zsm/tests/
        ├── test_attached_clients.py
        ├── test_layouts.py
        ├── test_session_info.py
        ├── test_session_parser.py
        └── test_state.py
```

### 2. `pyproject.toml` declara dos scripts

```toml
[project.scripts]
ztc = "ztc.__main__:main"
zsm = "ztc.sessions.__main__:main"
```

`uv tool install ztc` expone ambos comandos en PATH automaticamente. No hay que pelear con extras, `--with`, `--reinstall`, ni venvs separados.

### 3. PickerScreen reusable con dos callbacks: `on_launch` y `on_cancel`

`PickerScreen` se usa en dos contextos dentro del mismo paquete:

- **Standalone** (CLI `zsm`): `SessionLauncherApp` la monta como root screen. La logica historica es: `PickerScreen` setea `self.app.target = X; self.app.exit()`, y despues `ztc/sessions/__main__.py` lee `app.target` y hace `os.execvp`. **Ese flujo se preserva intacto en standalone.**
- **Embebida** (item "Zellij sessions" en menu de `ztc`): `TermConfigApp.push_screen(PickerScreen)`. Aqui el flujo standalone no funciona — `TermConfigApp` no tiene `target`, y `app.exit()` cerraria toda la app de configuracion sin ejecutar nada. Hay que invertir la responsabilidad: PickerScreen entrega el target via callback y el caller decide que hacer.

Por eso PickerScreen necesita **dos callbacks separados**, igual que el plan α (no es eliminable):

```python
from ztc.sessions.types import LaunchTarget

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
        # Comportamiento standalone: setear target + exit; __main__ hace execvp.
        self.app.target = target  # type: ignore[attr-defined]
        self.app.exit()

    def _default_cancel(self) -> None:
        # Comportamiento standalone: target=None + exit.
        self.app.target = None  # type: ignore[attr-defined]
        self.app.exit()
```

`SessionLauncherApp` no pasa callbacks (defaults = comportamiento historico, sin cambios). `TermConfigApp` pasa los dos:

- `on_launch=self._handle_session_launch` — un metodo que hace `os.execvp` directamente (sin pasar por `app.target`, porque `TermConfigApp` no tiene ese atributo).
- `on_cancel=lambda: self.pop_screen()` — vuelve al menu sin cerrar la app.

**Por que la consolidacion no elimina los callbacks**: el cambio entre plan α y plan γ es solo el modo de instalacion (un paquete vs dos). El **lifecycle** del lanzamiento (standalone setea-target-y-exit; embebido no puede hacer eso) es independiente del packaging y obliga a tener los callbacks de todas formas.

### 4. `LaunchTarget` en `ztc/sessions/types.py`

Hoy esta en `zsm/app.py:13`. Lo movemos a `ztc/sessions/types.py` para evitar el import circular (`ztc/sessions/app.py` ya importa `PickerScreen` desde `screens/`, y `screens/picker.py` necesitaria importar `LaunchTarget`).

### 5. Sin acoplamiento weak: import directo

```python
# ztc/app.py
from ztc.sessions.screens.picker import PickerScreen
```

Sin `try/except`, sin `HAS_ZSM`, sin `[project.optional-dependencies]`. La feature **siempre** esta disponible — el codigo es del mismo paquete.

### 6. Reorganizacion de docs

Todos los `.md` de planes/notes que viven hoy en la raiz se mueven a `doc/`. Beneficio doble: la raiz queda limpia para usuarios que clonan el repo, y `.gitignore` puede agregar reglas que prevengan que vuelvan a aparecer planes en raiz por accidente.

| Archivo | Destino |
|---|---|
| `README.md` | Raiz (sin cambios) |
| `AGENTS.md` | Raiz (sin cambios — ya esta en `.gitignore`, es de uso local) |
| `PLAN.md` | `doc/PLAN.md` |
| `PLAN_MULTI_TERMINAL.md` | `doc/PLAN_MULTI_TERMINAL.md` |
| `PLAN_TUI_FROM_ALACRITTY.md` | `doc/PLAN_TUI_FROM_ALACRITTY.md` |
| `PLAN_ZSM_INTEGRATION.md` | `doc/PLAN_ZSM_INTEGRATION.md` |
| `PLAN_ZSM_AS_SUBPACKAGE.md` (este) | `doc/PLAN_ZSM_AS_SUBPACKAGE.md` |
| `NOTES.md` | `doc/NOTES.md` |

Reglas nuevas en `.gitignore` que protegen contra accidentes:

```gitignore
# Planes/notas vivos en doc/, nunca en raiz.
/PLAN*.md
/NOTES.md
```

(El `/` inicial limita el patron a la raiz; archivos con esos nombres dentro de `doc/` siguen siendo trackeables.)

## Pasos de ejecucion

> **Orden de las fases**: la migracion de codigo (Fases 1-4) va primero; la reorganizacion de docs (Fase 5) va al final. La separacion deja claro el debugging si algo falla — un commit que solo mueve archivos `.md` no contamina el log de la migracion grande, y si la migracion se aborta el repo no queda en estado intermedio con docs movidos.

### Fase 1: Mover zsm a `ztc/sessions/` como subpaquete

Repo: `/home/martin/Documents/ztc`.

1. **Copiar el codigo de zsm como subpaquete de ztc**:
   ```bash
   cp -r /home/martin/Documents/zsm/src/zsm /home/martin/Documents/ztc/src/ztc/sessions
   ```

   **Sobre preservar git history (opcional)**: si querés que los commits de zsm aparezcan en el log de ztc con paths reescritos a `src/ztc/sessions/`, ejecutar en lugar del `cp`:
   ```bash
   cd /home/martin/Documents/ztc
   git subtree add --prefix=src/ztc/sessions /home/martin/Documents/zsm master
   ```
   Limita: deja un merge commit con history embebido. Si te molesta el ruido en el log, usa `cp` y listo. **Default del plan: `cp`** (mas simple, menos ruido).

2. **Reescribir imports** dentro de `src/ztc/sessions/`:
   - Toda ocurrencia de `from zsm.X` o `import zsm.X` → `from ztc.sessions.X` / `import ztc.sessions.X`.
   - Buscar todas las ocurrencias:
     ```bash
     grep -rn "from zsm\|import zsm" /home/martin/Documents/ztc/src/ztc/sessions/
     ```
   - Renombrar mecanicamente.

3. **Mover y reescribir tests**:
   ```bash
   mkdir /home/martin/Documents/ztc/tests/sessions
   cp /home/martin/Documents/zsm/tests/*.py /home/martin/Documents/ztc/tests/sessions/
   ```
   Reescribir imports en los tests:
   ```bash
   grep -rn "from zsm\|import zsm" /home/martin/Documents/ztc/tests/sessions/
   ```
   Misma sustitucion (`zsm.X` → `ztc.sessions.X`).

4. **Mover `LaunchTarget` a `ztc/sessions/types.py`** (hoy esta en `zsm/app.py:13` que ahora seria `ztc/sessions/app.py`):
   - Crear `ztc/sessions/types.py` con la definicion.
   - Actualizar `ztc/sessions/app.py` para importar desde `ztc.sessions.types`.

5. **Refactor de PickerScreen**: agregar parametros `on_launch` y `on_cancel` con defaults que reproducen el comportamiento standalone historico (ver Decision §3 mas arriba).
   - Importar `LaunchTarget` desde `ztc.sessions.types`.
   - Reemplazar las 3 ocurrencias de launch por `self._on_launch(target)`:
     - lineas 407-408 (attach): `self._on_launch(("attach", s.name, None))`
     - lineas 411-412 (bash): `self._on_launch(("bash", None, None))`
     - lineas 451-452 (new): `self._on_launch(("new", result.name, result.layout))`
   - Reemplazar la ocurrencia de cancel (lineas 575-576) por `self._on_cancel()`.
   - Los defaults `_default_launch` / `_default_cancel` setean `self.app.target` y hacen `self.app.exit()`, identico al comportamiento actual. `SessionLauncherApp` (ex `ZsmApp`) no necesita cambios — sigue leyendo `app.target` despues de `app.run()`.

6. **Actualizar `ztc/pyproject.toml`**:
   - Agregar al `[project.scripts]`:
     ```toml
     zsm = "ztc.sessions.__main__:main"
     ```
   - **No** agregar deps nuevas: zsm dependia de `textual`, `kdl-py`, `zellij-themes` — todas ya estan en ztc.
   - **Eliminar** (si llegan a estar) `[project.optional-dependencies] sessions = ...` y `[tool.uv.sources] zsm = ...`. (Si el plan α se hubiera ejecutado parcialmente; en el estado actual no estan, asi que skip.)

7. **Verificar**: correr los tests.
   - 208 existentes de ztc + 45 movidos de zsm = **253 tests deben pasar**.
   - Si algun test asume CWD o paths, ajustar.
   - Si hay colision de fixture o conftest, mover bajo `tests/sessions/conftest.py` aislado.

8. **Commit**: `refactor: integrar zsm como subpaquete ztc.sessions con CLI propio`.

### Fase 2: Item "Zellij sessions" en menu principal de ztc

Repo: `/home/martin/Documents/ztc`.

1. **`src/ztc/app.py`**:
   - Imports directos arriba del modulo:
     ```python
     import os
     from ztc.sessions.screens.picker import PickerScreen
     from ztc.sessions.services.zellij_session import attach_argv, new_session_argv
     ```
   - `_build_menu_options()`: agregar `Option(f"Zellij sessions{zellij_suffix}", id="sessions", disabled=zellij_disabled)` **inmediatamente despues de "Zellij layouts"**, antes de "Terminal colors". Reusa `zellij_suffix` y `zellij_disabled` ya calculados (`app.py:153-154`). Mismo patron que los items existentes.
   - `_on_menu_selected()`: nuevo branch para `event.option.id == "sessions"`:
     ```python
     elif event.option.id == "sessions":
         self.push_screen(
             PickerScreen(
                 on_launch=self._handle_session_launch,
                 on_cancel=lambda: self.pop_screen(),
             )
         )
     ```
     Los dos callbacks son obligatorios — ver Decision §3 para el motivo (TermConfigApp no tiene `target`, asi que el flujo standalone setea-target-y-exit no funciona embebido).
   - Nuevo metodo `_handle_session_launch` que recibe el target y hace `execvp` directamente, usando los helpers internos importados:
     ```python
     def _handle_session_launch(self, target):
         if target is None:
             return  # guard defensivo: cancel va por on_cancel, no deberia llegar acá.
         action, payload, extra = target
         if action == "attach":
             argv = attach_argv(payload or "")
         elif action == "new":
             argv = new_session_argv(payload or "", layout=extra)
         elif action == "bash":
             shell = os.environ.get("SHELL") or "/bin/bash"
             argv = [shell]
         else:
             return
         os.execvp(argv[0], argv)
     ```

2. **Verificar width del menu**: el item "Zellij sessions" extiende el ancho minimo. El ancho actual del logo es 25. Si "Zellij sessions" no entra, ajustar.

3. **Tests** en `tests/test_app_menu_gating.py` (o donde corresponda):
   - El menu tiene 4 items cuando zellij esta instalado.
   - El item Sessions aparece con suffix `(zellij not installed)` y disabled cuando `zellij_installed=False`.
   - `q/Esc` desde `PickerScreen` embebido vuelve al menu de ztc (no cierra la app).
   - **Test critico de launch embebido**: monkeypatchear `os.execvp` y verificar que cuando se selecciona attach/new/bash desde un `PickerScreen` montado dentro de `TermConfigApp`, `os.execvp` se invoca con el argv esperado (no se cierra ztc sin ejecutar nada). Ese test captura justo el bug de diseno que tenia el plan antes de esta correccion: si `PickerScreen` se monta sin `on_launch` y delega al default standalone, el flujo embebido no ejecuta execvp y la integracion queda silenciosamente rota.
   - **Actualizar tests existentes que navegan el menu por posicion**: al insertar "Zellij sessions" despues de "Zellij layouts", "Terminal colors" pasa de 3er item a 4to. Cualquier test con `pilot.press("down", "down", "enter")` para abrir Colors debe pasar a tres `down`, o mejor refactorizarse para abrir por id (`option_list.action_select_highlighted()` con id, o helper). Casos confirmados a actualizar: `tests/test_app_menu_gating.py:245` y `:287`.

4. **Commit**: `feat: agregar item Zellij sessions al menu principal con PickerScreen embebida`.

### Fase 3: Documentacion de usuario en README

Repo: `/home/martin/Documents/ztc`.

El `README.md` es el punto de entrada para usuarios finales. Despues del refactor tiene que cubrir tres cosas: como instalar, como usar (los dos comandos), y como funciona internamente lo justo para que el usuario no se sorprenda con el comportamiento de `zsm` (execvp, no es subprocess).

1. **Seccion "Installation"** (crear o actualizar):

   ```markdown
   ## Installation

   ```bash
   uv tool install ztc
   ```

   Esto instala dos comandos en PATH:

   - `ztc`: app completa con menu (themes, layouts, terminal colors, sessions).
   - `zsm`: launcher rapido de sesiones — equivalente a abrir `ztc` y elegir
     "Zellij sessions" desde el menu, pero sin pasar por el menu.

   ### Requisitos

   - Python 3.11+ (gestionado por uv).
   - Zellij (opcional). Si no esta instalado, los items de Zellij en el menu
     aparecen disabled con la nota `(zellij not installed)`.
   - Para edicion de colores de terminal: Alacritty o Kitty configurados.
   ```

2. **Seccion "Usage"** con los dos comandos:

   ```markdown
   ## Usage

   ### `ztc` — app completa

   Abre el menu con todas las features:

   - **Zellij theme**: elegir/editar el tema activo de Zellij.
   - **Zellij layouts**: gestionar layouts.
   - **Zellij sessions**: launcher de sesiones (equivalente a `zsm` directo).
   - **Terminal colors**: editar colores de Alacritty/Kitty sincronizados con el tema de Zellij.

   Navegacion: `↑↓` para moverte, `↲` para abrir, `q` para salir.

   ### `zsm` — launcher rapido de sesiones

   Abre directamente el selector de sesiones, sin pasar por el menu de ztc.
   Util como reemplazo del shell-prompt-to-zellij: cada vez que abris una
   terminal, ejecutas `zsm`, eligis attach/new/bash, y entras al destino.

   Atajos dentro del selector: `enter` attach, `n` new, `l` new+layout,
   `r` rename, `k` kill, `d` delete, `b` bash, `q` salir.
   ```

3. **Seccion "How it works"** (o "Architecture", al final del README) que explique el modelo de proceso. Esto evita confusion del usuario al observar que `zsm` "se cierra" al elegir attach — en realidad no se cierra, se reemplaza:

   ```markdown
   ## How it works

   ### `zsm` reemplaza su propio proceso al lanzar

   Cuando elegis attach/new/bash en `zsm`, no se abre Zellij como un proceso
   hijo — el comando usa `os.execvp` para **reemplazar** el proceso `zsm`
   por Zellij. Visualmente:

   ```
   shell (PID 100)
     └─ zsm (PID 200)         ← TUI corriendo
          │ elegis "attach mi-sesion"
          │ os.execvp("zellij", "attach", "mi-sesion")
          ↓
   shell (PID 100)
     └─ zellij (PID 200)      ← MISMO PID, distinto programa
          │ trabajas en zellij
          │ cerras zellij
          ↓
   shell (PID 100)            ← vuelve el control al shell
   ```

   Esto significa que `zsm` no consume memoria mientras estas en zellij —
   ya no existe como proceso, fue literalmente reemplazado.

   ### Misma logica para el item "Zellij sessions" desde `ztc`

   Cuando elegis attach/new/bash desde el menu embebido de ztc, el
   comportamiento es el mismo: ztc se reemplaza por Zellij. La unica
   diferencia es que `cancel` (Esc/q) vuelve al menu de ztc en lugar
   de salir al shell.

   ### Limitacion: `zsm`/ztc fuera de Zellij

   Las operaciones attach a otra sesion y crear nueva requieren que el
   proceso que las ejecuta **no este dentro de una sesion Zellij** — es una
   restriccion de Zellij, no del launcher. El caso de uso primario de `zsm`
   es ejecutarlo desde el shell antes de entrar a Zellij. Si lo invocas
   desde un pane de Zellij existente, esas operaciones van a fallar.
   ```

4. **Verificar links a `doc/`** si el README los menciona (probable que no).

5. **Commit**: `docs: README con installation, usage y modelo de proceso (execvp)`.

### Fase 4: Archivar repo zsm

Repo: `/home/martin/Documents/zsm`.

1. **Crear un commit final** en zsm que apunte a ztc:
   ```
   archive: zsm consolidado como subpaquete de ztc

   El codigo de este repo vive ahora en https://github.com/.../ztc
   bajo src/ztc/sessions/. El comando `zsm` sigue disponible
   instalando `uv tool install ztc`.

   Este repo queda en read-only / sin nuevas releases.
   ```

2. **Editar `README.md` de zsm** para que diga "moved to ztc/sessions" y apunte al nuevo repo.

3. **(Opcional)** archivar el repo en GitHub (si esta publicado): boton "Archive this repository".

4. **NO eliminar** el directorio local — sirve como referencia historica si despues hace falta consultar algun commit.

5. **Commit**: `archive: codigo migrado a ztc/sessions`.

### Fase 5: Reorganizacion de docs

Repo: `/home/martin/Documents/ztc`.

Esta fase va al final intencionalmente — ver nota al inicio de "Pasos de ejecucion".

1. Crear directorio `doc/`.
2. `git mv` cada uno de los 6 archivos a `doc/`. Usar `git mv` (no `mv`) para que git registre el rename y no rompa el blame:
   ```bash
   cd /home/martin/Documents/ztc
   mkdir -p doc
   git mv PLAN.md doc/
   git mv PLAN_MULTI_TERMINAL.md doc/
   git mv PLAN_TUI_FROM_ALACRITTY.md doc/
   git mv PLAN_ZSM_INTEGRATION.md doc/
   git mv PLAN_ZSM_AS_SUBPACKAGE.md doc/
   git mv NOTES.md doc/
   ```
3. Actualizar `.gitignore` con las dos reglas nuevas:
   ```gitignore
   # Planes/notas viven en doc/, nunca en raiz.
   /PLAN*.md
   /NOTES.md
   ```
4. Buscar referencias a los paths viejos en el codigo y otros docs:
   ```bash
   grep -rn "PLAN_\|NOTES.md" /home/martin/Documents/ztc --include="*.md" --include="*.py"
   ```
   Actualizar links si los hay (probable: `README.md` puede mencionar algun `PLAN_*.md`; este propio plan referencia a `PLAN_ZSM_INTEGRATION.md` con path relativo que sigue funcionando despues del move porque ambos estan en `doc/`).
5. **Commit**: `docs: mover planes y notas a doc/, gitignore para prevenir reaparicion en raiz`.

## Riesgos y consideraciones

### Verificacion exhaustiva de referencias a `zsm`

El refactor `zsm.X` → `ztc.sessions.X` tiene que cubrir tres tipos de referencia:

- **Imports** (`from zsm.X import ...`, `import zsm.X`).
- **Strings de monkeypatch / `unittest.mock.patch`** literales tipo `"zsm.services.zellij_session.shutil.which"`. Hay 10+ ocurrencias en `tests/test_attached_clients.py` que **no se detectan con un grep de imports**. Si se las saltea, los tests rompen silenciosamente porque el patch no encuentra el simbolo.
- Cualquier otra referencia textual al modulo `zsm` (docstrings que mencionen rutas, etc.).

Comando final post-refactor (busqueda amplia con `\bzsm\b` para captar todo, no solo imports):

```bash
rg -n "\bzsm\b" /home/martin/Documents/ztc/src/ztc/sessions /home/martin/Documents/ztc/tests/sessions
# Debe devolver: solo strings que conscientemente decidimos preservar
# (el comando CLI `zsm` en docstrings, paths de cache `~/.cache/zsm/`, etc.).
# Cualquier "zsm.X" en imports o monkeypatch debe pasar a "ztc.sessions.X".
```

### Cache/state path se preserva como `~/.cache/zsm/state.json`

`zsm/services/state.py:2` documenta que el cache vive en `~/.cache/zsm/state.json` (lo escribe `state.py` para recordar el ultimo layout usado). Al mover el modulo a `ztc/sessions/services/state.py`, **el path se preserva intencionalmente como `~/.cache/zsm/`** (no se migra a `~/.cache/ztc/`). Razones:

- El comando CLI `zsm` (que sigue existiendo como entry point) y el item embebido "Zellij sessions" comparten el mismo state — si fuera distinto, el last-layout no se sincronizaria entre las dos formas de invocar.
- Usuarios que vienen de zsm standalone preservan su historial sin migracion.

Decision explicita: el namespace del cache es de la **feature** (sesiones), no del paquete que la contiene. Mantener `zsm/` como nombre del cache es coherente con que el comando publico se siga llamando `zsm`.

### Conftest y fixtures de tests

Si `zsm/tests/` tiene `conftest.py` con fixtures que asumen layout de paquete `zsm`, hay que migrarlas. Verificar:
```bash
ls /home/martin/Documents/zsm/tests/conftest.py 2>/dev/null
```

### Doble entrada de `__main__`

`ztc/__main__.py` y `ztc/sessions/__main__.py` coexisten sin conflicto — Python las distingue por path. `python -m ztc` corre uno; `python -m ztc.sessions` corre el otro. Los CLIs `ztc` y `zsm` van por `[project.scripts]` y mapean explicitamente.

### `SessionLauncherApp` (antes `ZsmApp`)

El `app.py` de zsm define `ZsmApp`. Conviene renombrarlo a `SessionLauncherApp` (o `SessionsApp`) para que no quede el nombre `Zsm*` colgado dentro de un paquete `ztc.sessions`. Cosmetico pero coherente con la consolidacion. Cambio aplica solo en `ztc/sessions/app.py` y `ztc/sessions/__main__.py`.

### Tests de `test_app_menu_gating.py`

Hoy probablemente cuenta 3 items. Va a haber que ajustarlo a 4. Listar los tests que tocan el menu:
```bash
grep -n "menu\|Option\|build_menu" /home/martin/Documents/ztc/tests/test_app_menu_gating.py
```

### Reglas de `.gitignore` y archivos ya trackeados

Las reglas `/PLAN*.md` y `/NOTES.md` solo afectan archivos **untracked**. Los archivos que ya existen en raiz seguiran trackeados hasta que se haga `git mv` a `doc/`. Por eso Fase 5 hace los `git mv` antes de agregar las reglas al `.gitignore` — el orden inverso dejaria los archivos trackeados en raiz pero ignorando los nuevos que se intenten crear, estado inconsistente.

### El repo `zsm` deja de actualizarse

Si alguien (otro tu, otra persona) tiene `zsm` instalado de un release pre-archivo, sigue funcionando. Pero no hay updates. La via correcta para nuevos usuarios es `uv tool install ztc`. Documentarlo claro en el README de zsm archivado.

## Que dejamos sin tocar

- `zellij-themes` (paquete shared): sin cambios. Sigue como path source en `ztc/pyproject.toml`.
- Logica interna de `PickerScreen`: solo se agregan los callbacks `on_launch` y `on_cancel` (con defaults que reproducen el comportamiento standalone historico); el resto del comportamiento es identico.
- CLI de `zsm` desde el punto de vista del usuario: el comando `zsm` arranca PickerScreen igual que hoy. Misma UX, mismo execvp.

## Resumen ejecutivo

| | Antes (estado actual) | Despues |
|---|---|---|
| Paquetes pip | 2 separados (`zsm`, `ztc`) + 1 shared (`zellij-themes`) | 1 (`ztc`) + 1 shared (`zellij-themes`) |
| CLIs en PATH tras `uv tool install ztc` | Solo `ztc` | `ztc` + `zsm` (gratis) |
| Integracion en menu de ztc | No existe | Item "Zellij sessions" siempre disponible (gateado por `zellij_installed`) |
| Acoplamiento entre componentes | N/A | Import directo (mismo paquete) |
| Repo `zsm` independiente | Activo | Archivado, codigo movido a `ztc/sessions/` |
| Docs en raiz de ztc | 6 planes + NOTES + README + AGENTS | Solo README + AGENTS (resto a `doc/`) |
| `.gitignore` | Permitia planes en raiz | Reglas que previenen reaparicion |
| Tests | 208 ztc + 45 zsm | 253 ztc (incluye los movidos) |
