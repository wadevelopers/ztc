# Plan: consolidar `zellij-themes` en ztc + reorganizar namespace de Zellij

> **Prerequisito de [`PLAN_TERMINAL_SETTINGS.md`](PLAN_TERMINAL_SETTINGS.md)**. Debe ejecutarse y cerrarse antes de empezar Fase 1 de aquel plan. Aquel asume `colors` ya en `ztc.services.colors` y stuff de Zellij ya en `ztc.zellij.X`.

## Contexto y motivacion

`zellij-themes` se concibio como **paquete shared pip** porque dos apps independientes lo usaban: `ztc` (la app de configuracion) y `zsm` (el launcher de sesiones). La separacion tenia sentido cuando ambas eran deployables independientemente.

Despues de [`PLAN_ZSM_AS_SUBPACKAGE.md`](PLAN_ZSM_AS_SUBPACKAGE.md), `zsm` se consolido como subpaquete `ztc.sessions`. **Hoy `zellij-themes` es usado solo por `ztc`.** La premisa "shared library" desaparecio. Mantenerlo como repo y paquete pip separado es ruido sin beneficio.

Ademas, durante el analisis para agregar settings de terminal (padding, opacity, etc.) descubrimos otro problema estructural: `zellij-themes/colors.py` aloja `CanonicalSlot`, `is_valid_hex`, `compute_warnings` — eso es **stuff de terminal** (Alacritty/Kitty), no de Zellij. Esta ahi por accidente historico.

Y un tercer problema relacionado: `ztc/services/zellij_themes.py` y `zellij_config.py` son wrappers que **mezclan escritura propia con re-exports del shared**, ocultando el boundary entre lectura y escritura. Esos services tambien son de Zellij, deberian agruparse con el resto.

Este plan resuelve los tres problemas en un mismo refactor: consolida `zellij-themes` adentro de `ztc`, agrupa TODO lo de Zellij bajo un namespace coherente (`ztc/zellij/`), y mueve lo que es de terminal a su lugar correcto (`ztc/services/colors.py`).

## Alcance

### Adentro

- **Disolver el paquete pip `zellij-themes`**: codigo + assets + tests viajan a `ztc`.
- **Reorganizar a `ztc/zellij/`** (Opcion B en la discusion): TODO lo de Zellij (lectura + escritura + models + assets) vive bajo un solo namespace coherente. Sin re-exports artificiales.
- **Mover `colors`** a `ztc/services/colors.py`: stuff de terminal donde corresponde.
- **Renombrar lo que estaba mal nombrado** durante el refactor:
  - `ztc/services/zellij_themes.py` (escritura) → `ztc/zellij/theme_writer.py`.
  - `ztc/services/zellij_config.py` (escritura) → `ztc/zellij/config_ops.py`.
  - `ztc/services/kdl_io.py` (es 100% layout-specific) → `ztc/zellij/layout_io.py`.
- **Archivar repo `zellij-themes`** (igual que se hizo con `zsm`).

### Afuera

- **Refactorizar la API publica de los modulos** (signatures, comportamiento): NO. Esto es solo movimiento + renombre. La logica de cada funcion no cambia.
- **Cambiar el comportamiento user-facing**: NO. `zsm` standalone sigue funcionando idéntico. Los temas built-in se cargan igual. La sincronizacion con el tema activo de Zellij funciona igual.
- **Tocar `zsm` (subpaquete `ztc.sessions`)**: solo actualizar imports a los nuevos paths. No cambia comportamiento.

### No se preserva

- Git history del repo `zellij-themes` (similar a la decision de zsm: simple `cp` y archivado, no `git subtree`). El repo queda como referencia.

## Estructura final

### Antes (estado actual)

```
ztc/                                  ← repo principal
├── pyproject.toml                    ← declara dep zellij-themes via path
├── src/ztc/
│   ├── services/
│   │   ├── zellij_themes.py          ← escritura del bloque themes (de ztc) + re-exports
│   │   ├── zellij_config.py          ← escritura de config.kdl (de ztc) + re-exports
│   │   ├── kdl_io.py                 ← layout-specific aunque el nombre sugiere genérico
│   │   ├── layout_ops.py             ← operaciones sobre Layout (Zellij)
│   │   ├── theme_sync.py             ← cruza zellij + terminal
│   │   ├── terminals/
│   │   ├── runtime_detect.py
│   │   ├── atomic.py
│   │   ├── backups.py
│   │   └── toml_io.py
│   ├── sessions/                     ← subpaquete ex-zsm (sin cambios)
│   ├── screens/
│   ├── widgets/
│   ├── models/
│   └── ...
└── tests/

zellij-themes/                        ← repo separado (a archivar)
├── pyproject.toml
├── src/zellij_themes/
│   ├── __init__.py
│   ├── colors.py                     ← stuff de TERMINAL (mal lugar)
│   ├── config.py                     ← lectura del tema activo
│   ├── models.py
│   ├── theme_assets.py               ← built-in themes + builders Textual
│   ├── user_themes.py                ← parsing de user themes
│   └── assets/zellij_themes/*.kdl
└── tests/
    └── test_basic.py
```

### Despues (objetivo)

```
ztc/                                  ← repo principal (incluye todo)
├── pyproject.toml                    ← sin dep path zellij-themes
├── src/ztc/
│   ├── zellij/                       ← TODO lo de Zellij (NUEVO subpaquete)
│   │   ├── __init__.py               ← re-exports limpios
│   │   ├── theme_assets.py           ← (de ex-shared)
│   │   ├── user_themes.py            ← (de ex-shared) lectura/parsing
│   │   ├── config.py                 ← (de ex-shared) lectura del tema activo
│   │   ├── models.py                 ← (de ex-shared) dataclasses
│   │   ├── theme_writer.py           ← era ztc/services/zellij_themes.py
│   │   ├── config_ops.py          ← era ztc/services/zellij_config.py
│   │   ├── layout_io.py              ← era ztc/services/kdl_io.py (renombrado)
│   │   ├── layout_ops.py             ← era ztc/services/layout_ops.py
│   │   └── assets/zellij_themes/*.kdl
│   ├── services/                     ← genérico / cross-cutting
│   │   ├── colors.py                 ← era zellij-themes/colors.py (stuff de terminal)
│   │   ├── theme_sync.py             ← (sin moverse: cruza zellij + terminal)
│   │   ├── terminals/                ← (sin cambios)
│   │   ├── runtime_detect.py
│   │   ├── atomic.py
│   │   ├── backups.py
│   │   └── toml_io.py
│   ├── sessions/                     ← (subpaquete ex-zsm; solo actualiza imports)
│   ├── screens/
│   ├── widgets/
│   ├── models/
│   └── ...
└── tests/
    ├── zellij/                       ← migrados de zellij-themes/tests/
    │   └── test_basic.py
    └── (otros tests existentes)

zellij-themes/                        ← archivado, no se publica nuevas releases
└── README.md (apunta a ztc/zellij/)
```

## Decisiones de diseno

### 1. `ztc.zellij` como home unico de TODO lo de Zellij

Lectura, escritura, models, assets, parsing, builders Textual. **Sin re-exports artificiales** entre lectura y escritura — ambas conviven en el mismo subpaquete y los call sites importan directamente lo que necesitan:

```python
# Antes
from ztc.services.zellij_themes import save_user_theme   # escritura, wrapper que tambien re-exporta lectura
from zellij_themes.user_themes import list_user_themes   # lectura desde shared

# Despues
from ztc.zellij.theme_writer import save_user_theme       # escritura
from ztc.zellij.user_themes import list_user_themes       # lectura
```

### 2. `ztc.services.colors` para stuff de terminal

`CanonicalSlot`, `Warning`, `compute_warnings`, `is_valid_hex`, `normalize_hex`, `contrast_ratio`, helpers internos (`_hex_to_rgb`, `_rel_luminance`). Es shared entre los backends Alacritty/Kitty pero **no es de Zellij**.

### 3. `theme_sync.py` queda en `services/`

Es el unico modulo que cruza ambos namespaces (lee del tema Zellij + escribe al backend de terminal). Vive en `services/` como cross-cutting, no en `zellij/`. Sus imports apuntan a ambos lados:

```python
from ztc.zellij import theme_assets
from ztc.services import colors
from ztc.services.terminals import TerminalBackend
```

### 4. Renames coherentes

Aprovechamos el refactor para renombrar archivos cuyo nombre era enganoso:

| Original | Nuevo | Por que |
|---|---|---|
| `services/zellij_themes.py` | `zellij/theme_writer.py` | Es escritura del bloque themes; mezclar con el shared `zellij_themes/` que era lectura era confuso. |
| `services/zellij_config.py` | `zellij/config_ops.py` | Tiene `set_active_theme` (escritura), `list_layouts` (lectura) y `zellij_setup_check` (verificacion). El nombre `_writer` que use originalmente era erroneo — `_ops` describe mejor las 3 responsabilidades. |
| `services/kdl_io.py` | `zellij/layout_io.py` | El archivo es 100% layout-specific (`load_layout`, `dump_layout`, `_parse_tab`, etc.); el nombre `kdl_io` sugeria un parser KDL genérico que no es. |

### 5. Re-exports limpios en `ztc/zellij/__init__.py`

Replica exactamente la estructura de `zellij_themes/__init__.py` actual (re-exporta los modulos top-level + constantes/clases publicas), ajustada a la nueva ubicacion. **Sin duplicar `TEXTUAL_FALLBACK` como string** — viene de `user_themes` para evitar drift:

```python
# ztc/zellij/__init__.py
"""Stuff de Zellij: lectura de temas built-in vendorizados, parsing de
user themes, builders Textual, lectura de tema activo, models, escritura
de bloques themes/config, layouts.

Esta API publica replica la que tenia el ex-shared `zellij_themes/`
(re-exports de modulos top-level + simbolos mas usados), asi los call
sites pasan de `from zellij_themes import X` a `from ztc.zellij import X`
con cambio mecanico.
"""
from ztc.zellij import (
    config,
    config_ops,
    layout_io,
    layout_ops,
    models,
    theme_assets,
    theme_writer,
    user_themes,
)
from ztc.zellij.models import ZellijColor, ZellijTheme
from ztc.zellij.user_themes import TEXTUAL_FALLBACK

__all__ = [
    "TEXTUAL_FALLBACK",
    "ZellijColor",
    "ZellijTheme",
    "config",
    "config_ops",
    "layout_io",
    "layout_ops",
    "models",
    "theme_assets",
    "theme_writer",
    "user_themes",
]
```

`colors` **no se re-exporta** desde `ztc.zellij` — vive en `ztc.services.colors` porque es de terminal, no de Zellij.

### 6. Comportamiento de `zsm` standalone se preserva

`ztc/sessions/app.py` usa hoy:

```python
from zellij_themes import theme_assets, user_themes
from zellij_themes import TEXTUAL_FALLBACK
from zellij_themes.config import read_active_theme
```

Despues del refactor:

```python
from ztc.zellij import theme_assets, user_themes
from ztc.zellij import TEXTUAL_FALLBACK
from ztc.zellij.config import read_active_theme
```

El codigo adentro de cada modulo es identico; solo cambia el path. `zsm` standalone (CLI invocable desde el shell) sigue cargando los mismos `.kdl` vendorizados, parseando el mismo `~/.config/zellij/config.kdl`, sincronizando el tema Textual igual.

## Pasos de ejecucion

### Fase 0: Pre-condicion — worktree limpio

Antes de empezar:

```bash
git -C /home/martin/Documents/ztc status -s
```

Debe estar vacio (o solo con archivos untracked que no participen del refactor). Si hay cambios pending (por ejemplo, ajustes UI hechos antes y aun no commiteados), commitearlos primero o `git stash` — sino se van a mezclar con los renames/imports del refactor y va a ser dificil revisar el diff de cada commit del plan.

Lo mismo en zellij-themes: `git -C /home/martin/Documents/zellij-themes status -s` debe estar limpio.

### Fase 1: Crear `ztc/zellij/` con stuff ex-shared

Repo: `/home/martin/Documents/ztc`.

1. **Copiar el codigo de `zellij-themes` a `ztc/zellij/`** (sin `colors.py`):
   ```bash
   mkdir -p src/ztc/zellij
   cp -r /home/martin/Documents/zellij-themes/src/zellij_themes/{config,models,theme_assets,user_themes}.py src/ztc/zellij/
   cp -r /home/martin/Documents/zellij-themes/src/zellij_themes/assets src/ztc/zellij/
   # Limpiar caches que pueden venir en el cp -r recursivo:
   find src/ztc/zellij -name __pycache__ -type d -prune -exec rm -rf {} +
   find src/ztc/zellij -name "*.pyc" -delete
   ```
2. **Crear `ztc/zellij/__init__.py`** con los re-exports limpios (ver Decision §5). Usar el `__init__.py` actual de `zellij_themes` como referencia, ajustando los paths a `ztc.zellij.X`.
3. **Crear `ztc/services/colors.py`** con todo el contenido actual de `zellij-themes/src/zellij_themes/colors.py`.
4. **Actualizar imports internos en los archivos copiados** (ademas de `ASSETS_PACKAGE` que esta en el siguiente paso). Los modulos shared se importan entre si — al copiarlos a `ztc/zellij/`, esos imports siguen apuntando a `zellij_themes.X` y hay que reescribirlos a `ztc.zellij.X`. Casos identificados:
   - `ztc/zellij/user_themes.py:20`: `from zellij_themes.models import ZellijColor, ZellijTheme` → `from ztc.zellij.models import ZellijColor, ZellijTheme`. Verificar si hay mas imports a `zellij_themes` en este archivo (linea ~58 segun grep) y migrarlos todos.
   - Cualquier otro archivo copiado que importe `from zellij_themes.X` debe reescribirse a `from ztc.zellij.X`.
   - Comando para listar todos los imports residuales en lo copiado:
     ```bash
     rg -n "from zellij_themes|import zellij_themes" /home/martin/Documents/ztc/src/ztc/zellij/
     # Despues del paso, debe devolver: nada.
     ```
5. **Actualizar `ASSETS_PACKAGE` en `ztc/zellij/theme_assets.py`** (linea 39 del archivo copiado): `"zellij_themes.assets.zellij_themes"` → `"ztc.zellij.assets.zellij_themes"`. Este string se pasa a `importlib.resources.files()` (lineas 120, 131, 153) — sin actualizarlo, la carga de built-in themes falla en runtime aunque los archivos esten copiados.
6. **Configurar `force-include` en `pyproject.toml` de ztc** para empacar los assets en el wheel:
   ```toml
   [tool.hatch.build.targets.wheel.force-include]
   "src/ztc/zellij/assets/zellij_themes" = "ztc/zellij/assets/zellij_themes"
   ```
   `[tool.hatch.build.targets.wheel] packages = ["src/ztc"]` empaca los `.py` recursivamente, pero los `.kdl` (no-Python) requieren `force-include`. Es lo que hace hoy `zellij-themes/pyproject.toml` y por eso el shared actual lo tiene; al consolidar hay que replicarlo.

### Fase 2: Mover los services de Zellij a `ztc/zellij/`

1. **`git mv src/ztc/services/zellij_themes.py src/ztc/zellij/theme_writer.py`**.
2. **`git mv src/ztc/services/zellij_config.py src/ztc/zellij/config_ops.py`**.
3. **`git mv src/ztc/services/kdl_io.py src/ztc/zellij/layout_io.py`**.
4. **`git mv src/ztc/services/layout_ops.py src/ztc/zellij/layout_ops.py`**.

### Fase 3: Actualizar imports en todo `ztc`

Reemplazos mecanicos directos (sustitucion 1:1 por modulo de origen):

| Patron viejo | Patron nuevo |
|---|---|
| `from zellij_themes.colors import X` | `from ztc.services.colors import X` |
| `from zellij_themes import colors` | `from ztc.services import colors` |
| `from zellij_themes.theme_assets import X` | `from ztc.zellij.theme_assets import X` |
| `from zellij_themes.user_themes import X` | `from ztc.zellij.user_themes import X` |
| `from zellij_themes.config import X` | `from ztc.zellij.config import X` |
| `from zellij_themes.models import X` | `from ztc.zellij.models import X` |
| `from zellij_themes import X` (X = `theme_assets` / `user_themes` / `config` / `models` / `TEXTUAL_FALLBACK`) | `from ztc.zellij import X` |
| `from ztc.services.kdl_io import X` | `from ztc.zellij.layout_io import X` |
| `from ztc.services.layout_ops import X` | `from ztc.zellij.layout_ops import X` |

**Reemplazos por simbolo (NO por modulo) para `zellij_themes` y `zellij_config` services**:

`ztc.services.zellij_themes` mezcla escritura propia con re-exports de lectura del shared. La sustitucion mecanica `→ theme_writer` es **incorrecta** para los simbolos de re-export — esos vienen del shared y deben apuntar a su modulo real en `ztc.zellij.X`. Tabla por simbolo:

| Simbolo importado de `ztc.services.zellij_themes` | Modulo destino |
|---|---|
| `read_active_theme` | `ztc.zellij.config` |
| `ZellijTheme`, `ZellijColor` | `ztc.zellij.models` |
| `TEXTUAL_FALLBACK` | `ztc.zellij` (re-export top-level) |
| `LEGACY_SLOTS`, `is_valid_theme_name`, `list_user_themes`, `list_all_themes`, `list_builtin_themes`, `builtin_theme_names` | `ztc.zellij.user_themes` |
| `find_themes_block`, `derive_rich_block`, `render_themes_block`, `save_user_themes`, `upsert_user_theme`, `delete_user_theme`, `clone_theme`, `display_slot`, `get_rich_slot`, `set_rich_slot`, `unset_rich_slot`, `default_legacy_slots` | `ztc.zellij.theme_writer` (escritura genuina; el `git mv` de Fase 2 lo deja ahi) |

Idem para `ztc.services.zellij_config`:

| Simbolo importado de `ztc.services.zellij_config` | Modulo destino |
|---|---|
| `read_active_theme` | `ztc.zellij.config` (lectura, viene del shared) |
| `set_active_theme` y demas escritura local | `ztc.zellij.config_ops` (el `git mv` de Fase 2 lo deja ahi) |

**Como ejecutar este paso**: para los call sites que importan de `ztc.services.zellij_themes` o `ztc.services.zellij_config`, **revisar caso por caso** qué simbolo importa y aplicar la fila correcta de la tabla. No hay sustitucion regex segura — solo lectura de cada import + decision.

**Archivos a revisar** (ya identificados via grep):

- `src/ztc/app.py` (importa zellij_themes via theme_assets, theme_sync, etc.).
- `src/ztc/services/theme_sync.py`.
- `src/ztc/services/terminals/__init__.py`, `alacritty.py`, `kitty.py` (CanonicalSlot).
- `src/ztc/zellij/theme_writer.py` (ya movido en Fase 2; revisar imports internos — viene de `services/zellij_themes.py` que tenia re-exports).
- `src/ztc/zellij/config_ops.py` (idem, viene de `services/zellij_config.py`).
- `src/ztc/screens/color_editor.py`.
- `src/ztc/screens/theme_editor.py`.
- `src/ztc/screens/layout_*.py`.
- `src/ztc/screens/custom_theme_editor.py`.
- `src/ztc/widgets/confirm.py` (is_valid_hex, normalize_hex).
- `src/ztc/sessions/app.py` (3 imports de zellij_themes).
- `src/ztc/sessions/screens/picker.py` (verificar).
- `tests/test_terminal_alacritty.py`, `test_terminal_kitty.py`, `test_theme_sync.py`, etc.

**Verificacion final**: cero referencias residuales en `src` y `tests`. Usar grep amplio (`\bzellij_themes\b`) para captar tambien strings de monkeypatch (`patch("zellij_themes.X.Y")`), no solo `from`/`import`. Excluir el path interno de assets (`ztc.zellij.assets.zellij_themes`) que **debe** seguir mencionando "zellij_themes" como subdir:

```bash
rg -n "\bzellij_themes\b|ztc\.services\.(zellij_themes|zellij_config|kdl_io|layout_ops)" \
   /home/martin/Documents/ztc/src /home/martin/Documents/ztc/tests \
   | grep -vE "ztc\.zellij\.assets\.zellij_themes|ztc/zellij/assets/zellij_themes"
# Debe devolver: nada (los matches del path interno de assets se excluyen).
# Pueden quedar menciones en docs/ — esas son aceptables (planes historicos).
```

### Fase 4: Migrar tests de `zellij-themes`

1. `mkdir -p tests/zellij`
2. `cp /home/martin/Documents/zellij-themes/tests/test_basic.py tests/zellij/test_basic.py`
3. **Actualizar imports en `test_basic.py`**: `from zellij_themes` → `from ztc.zellij` (excepto el `assert hasattr(zellij_themes, "colors")` de la linea 10, que se elimina porque colors ya no esta en ese namespace).
4. Si hace falta, agregar `tests/zellij/__init__.py` vacio.

### Fase 5: Actualizar `pyproject.toml` y eliminar dep path

1. Quitar de `pyproject.toml`:
   ```toml
   dependencies = [
       ...,
       "zellij-themes",  # ← QUITAR
       ...,
   ]

   [tool.uv.sources]
   zellij-themes = { path = "../zellij-themes", editable = true }   # ← QUITAR
   ```
2. Verificar: `uv sync` corre limpio sin la dep path.
3. Verificar: `uv run pytest` pasa todos los tests (incluidos los movidos de zellij-themes).

### Fase 6: Verificacion final

**Antes de archivar nada**: confirmar que ztc funciona sin la dep externa. Si algo falla aqui, hay que iterar — y tener el repo `zellij-themes` todavia activo permite revertir/depurar mas facil.

1. **Tests verdes en ztc**:
   ```bash
   uv run --directory /home/martin/Documents/ztc pytest
   # Esperado: ~265 (257 actuales + 8 migrados de zellij-themes).
   ```
2. **Build/install limpio**:
   ```bash
   cd /home/martin/Documents/ztc && uv sync --extra dev
   ```
3. **Verificacion manual de `zsm` standalone**:
   ```bash
   PATH=/usr/local/bin:/usr/bin:/bin /home/martin/.local/bin/uv run --directory /home/martin/Documents/ztc zsm
   ```
   La pantalla del PickerScreen debe verse igual que antes (mismo tema activo, mismo TUI). Si tenes Zellij en otra terminal: el listado de sesiones tambien.
4. **Verificacion manual de ztc**:
   ```bash
   uv run --directory /home/martin/Documents/ztc ztc
   ```
   Menu principal con sus 4 items, themes/layouts/sessions/colors funcionando.
5. **Verificar carga de built-in themes**: dentro de ztc, abrir el item "Zellij themes" y confirmar que la lista muestra los ~40 temas vendorizados. Si la lista esta vacia, `ASSETS_PACKAGE` no se actualizo (Fase 1 §4) o `force-include` falto (Fase 1 §5).

### Fase 7: Documentacion

1. **README.md**: actualizar links si menciona `zellij-themes` (probable que no, pero verificar). Considerar si vale la pena mencionar en "How it works" que el paquete esta consolidado.
2. **doc/PLAN_TERMINAL_SETTINGS.md**: ya tiene la nota de prerequisito; verificar que las referencias a paths esten actualizadas (`ztc.services.colors`, `ztc.zellij.X`).

### Fase 8: Archivar repo `zellij-themes`

**Solo despues de que Fase 6 cerro verde**. Si la verificacion fallo y queda algo por ajustar, archivar prematuramente entierra el contexto historico necesario para depurar.

Repo: `/home/martin/Documents/zellij-themes`.

1. **Reescribir `README.md`** con aviso "moved to ztc/zellij/" + apunta al destino. Mismo patron que el README final de zsm.
2. **Commit final** en zellij-themes:
   ```
   archive: codigo migrado a ztc/zellij/

   Este repo queda archivado. El codigo de zellij_themes vive ahora
   como subpaquete de ztc bajo src/ztc/zellij/. La razon historica
   (compartir entre ztc y zsm) desaparecio cuando zsm se consolido
   en ztc.sessions (PLAN_ZSM_AS_SUBPACKAGE.md).

   Read-only desde aca.
   ```
3. **NO eliminar** el directorio local — referencia historica.

## Riesgos y consideraciones

### Volumen del refactor

~15-20 archivos modifican imports. Riesgo de imports residuales no detectados (especialmente strings de monkeypatch en tests). Mitigacion: el grep de verificacion final (Fase 3) tiene que devolver cero. Si algo se escapa, los tests fallan.

### `theme_sync.py` cruza ambos namespaces

Es el unico modulo que importa de `ztc.zellij` Y de `ztc.services.colors` Y de `ztc.services.terminals`. Es esperable y correcto que viva en `services/` como cross-cutting. No es bug.

### Imports diferidos en `app.py` (lazy imports dentro de funciones)

Algunos modulos hacen `from zellij_themes import X` adentro de funciones (lazy). El grep los detecta pero el editor mecanico (sed) los puede saltear si solo busca al tope del archivo. Mitigacion: revisar archivo por archivo en Fase 3, no automatizar.

### Repo `zellij-themes` queda como referencia

Igual que zsm: NO eliminar local. Permite consultar history si despues hace falta.

## Que dejamos sin tocar

- `ztc/sessions/` (= zsm consolidado): solo se actualizan imports en sus archivos, el comportamiento es idéntico.
- API publica de cada modulo: signatures iguales, comportamiento igual.
- Tests existentes: 257 pasan exactamente igual que antes (mas los 8 migrados = 265).
- Comportamiento user-facing: 0 diferencia.

## Resumen ejecutivo

| | Antes | Despues |
|---|---|---|
| Paquetes pip | 2 (`ztc`, `zellij-themes`) | 1 (`ztc`) |
| Repos activos | 2 (ztc, zellij-themes; zsm ya archivado) | 1 (ztc) |
| Stuff de Zellij | mezclado: parte en shared, parte en services con re-exports | TODO en `ztc/zellij/` (lectura, escritura, models, layout, assets) |
| Stuff de terminal | en shared (`zellij_themes/colors.py` — mal lugar) | `ztc/services/colors.py` (lugar correcto) |
| Re-exports artificiales | sí (services/zellij_themes.py mezcla escritura + re-export de lectura) | no (cada caller importa directo del modulo correspondiente) |
| Naming | engañoso (`kdl_io.py` que es layout-specific; dos `zellij_themes` con mismo nombre) | coherente (`layout_io.py`, `theme_writer.py`, etc.) |
| Tests | 257 ztc + 8 zellij-themes (separados) | 265 ztc (consolidados) |
| `zsm` standalone | `uv tool install ztc` (con dep path zellij-themes) | `uv tool install ztc` (sin deps externas) |
| Comportamiento user-facing | (baseline) | identico |
