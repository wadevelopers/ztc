from __future__ import annotations

from pathlib import Path

import kdl

from term_config_tui.models.theme import ZellijColor, ZellijTheme

# Lista conocida de temas que vienen con Zellij. Se puede ampliar segun versiones.
# Si el usuario aplica un tema fuera de esta lista, no es un error: Zellij
# lo resuelve por nombre.
BUILTIN_DARK = (
    "ao",
    "ayu-dark",
    "ayu-mirage",
    "catppuccin-frappe",
    "catppuccin-macchiato",
    "catppuccin-mocha",
    "cyber-noir",
    "default",
    "dracula",
    "everforest-dark",
    "gruber-darker",
    "kanagawa",
    "lucario",
    "menace",
    "night-owl",
    "nightfox",
    "one-half-dark",
    "onedark",
    "retro-wave",
    "solarized-dark",
    "terafox",
    "tokyo-night",
    "tokyo-night-dark",
    "tokyo-night-storm",
    "vesper",
)

BUILTIN_LIGHT = (
    "ayu-light",
    "catppuccin-latte",
    "dayfox",
    "everforest-light",
    "gruvbox-light",
    "iceberg-light",
    "solarized-light",
    "tokyo-night-light",
)

BUILTIN_THEMES: tuple[str, ...] = tuple(sorted(set(BUILTIN_DARK + BUILTIN_LIGHT)))


def list_builtin_themes() -> list[ZellijTheme]:
    """Devuelve los temas built-in conocidos. Sin colores asociados."""
    return [ZellijTheme(name=n, source="builtin") for n in BUILTIN_THEMES]


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
        for child in theme_node.nodes:
            if not child.args:
                continue
            value = child.args[0]
            if not isinstance(value, str):
                continue
            colors.append(ZellijColor(name=child.name, value=value))
        out.append(
            ZellijTheme(name=theme_node.name, source="user", colors=colors)
        )
    return out


def list_all_themes(config_path: Path) -> list[ZellijTheme]:
    """Combina built-in + user. User tiene prioridad si hay colision de nombre."""
    user = list_user_themes(config_path)
    user_names = {t.name for t in user}
    builtins = [t for t in list_builtin_themes() if t.name not in user_names]
    return sorted(user + builtins, key=lambda t: (t.source != "user", t.name))
