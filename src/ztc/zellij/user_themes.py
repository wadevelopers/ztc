"""Lectura de temas declarados en `config.kdl` del usuario.

Read-only: solo parsea el bloque `themes { ... }` y devuelve modelos
`ZellijTheme`. Las operaciones de escritura (save, upsert, delete,
clone) quedan en las apps que editan el config — este shared package
es agnostico de la edicion.

Tambien expone helpers para listar built-in themes (cuyos hex viven
en los .kdl vendorizados) y para combinar user + built-in con
prioridad para los user.
"""

from __future__ import annotations

import re
from pathlib import Path

import kdl

from ztc.zellij.models import ZellijColor, ZellijTheme

# Slots de la "Paleta ANSI": fg/bg + 8 colores normales. Mapean 1:1 con
# Alacritty (primary.{foreground,background} + normal.{8 ANSI}). No
# incluyen `orange` porque Alacritty no tiene ese concepto: en el modelo
# nuevo, orange vive en text_unselected.emphasis_0 (rich) y solo Zellij
# lo consume.
LEGACY_SLOTS: tuple[str, ...] = (
    "fg",
    "bg",
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
)

_VALID_THEME_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]*$")

# Tema Textual al que caer cuando el activo de Zellij no esta registrado.
TEXTUAL_FALLBACK = "textual-dark"

# Excluimos 'ansi' del listing y registro porque usa indices de paleta del
# terminal (0..15) en vez de RGB. No podemos construir un Textual Theme
# desde el sin saber la paleta del terminal del usuario.
_EXCLUDED_BUILTINS = frozenset({"ansi"})


def is_valid_theme_name(name: str) -> bool:
    return bool(_VALID_THEME_NAME.match(name))


def builtin_theme_names() -> tuple[str, ...]:
    """Nombres de los temas built-in vendorizados en assets/zellij_themes/.
    Excluye 'ansi' (formato palette-index, sin RGB)."""
    from ztc.zellij import theme_assets

    names = [
        n for n in theme_assets.list_bundled_theme_names()
        if n not in _EXCLUDED_BUILTINS
    ]
    return tuple(sorted(names))


def list_builtin_themes() -> list[ZellijTheme]:
    """Devuelve los temas built-in. Sin colores asociados (los hex viven
    en los .kdl vendorizados; este listado solo expone nombres)."""
    return [ZellijTheme(name=n, source="builtin") for n in builtin_theme_names()]


def list_user_themes(config_path: Path) -> list[ZellijTheme]:
    """Extrae los temas del bloque `themes { ... }` en config.kdl.

    Tolera tanto el formato legacy con slots simples (fg, bg, red, ...) como
    el formato nuevo con componentes UI (text_unselected, ribbon_selected, ...):
    en cualquier caso recoge cada hijo directo como `ZellijColor`.
    """
    if not config_path.exists():
        return []
    try:
        doc = kdl.parse(config_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    themes_node = next((n for n in doc.nodes if n.name == "themes"), None)
    if themes_node is None:
        return []

    out: list[ZellijTheme] = []
    for theme_node in themes_node.nodes:
        colors: list[ZellijColor] = []
        raw_components: list = []
        for child in theme_node.nodes:
            if child.nodes:
                # Bloque anidado (formato nuevo): text_selected { ... }, etc.
                raw_components.append(child)
                continue
            if not child.args:
                continue
            value = child.args[0]
            if not isinstance(value, str):
                continue
            colors.append(ZellijColor(name=child.name, value=value))
        out.append(
            ZellijTheme(
                name=theme_node.name,
                source="user",
                colors=colors,
                raw_components=raw_components,
            )
        )
    return out


def list_all_themes(config_path: Path) -> list[ZellijTheme]:
    """Combina built-in + user. User tiene prioridad si hay colision de nombre."""
    user = list_user_themes(config_path)
    user_names = {t.name for t in user}
    builtins = [t for t in list_builtin_themes() if t.name not in user_names]
    return sorted(user + builtins, key=lambda t: (t.source != "user", t.name))
