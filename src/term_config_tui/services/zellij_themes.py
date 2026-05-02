from __future__ import annotations

import re
from pathlib import Path

import kdl

from term_config_tui.models.theme import ZellijColor, ZellijTheme
from term_config_tui.services.atomic import write_atomic
from term_config_tui.services.backups import make_backup

# Slots del formato legacy (los que usa custom_dark del usuario).
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
    "orange",
)

_VALID_THEME_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]*$")


def is_valid_theme_name(name: str) -> bool:
    return bool(_VALID_THEME_NAME.match(name))

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


# ---------- splice del bloque themes { ... } ----------

_THEMES_HEADER = re.compile(r"^themes\s*\{", re.MULTILINE)


def find_themes_block(text: str) -> tuple[int, int] | None:
    """Devuelve (start, end_exclusive) del nodo `themes { ... }` con balance de llaves.

    Tolera llaves dentro de strings ("...") y escapes (\\"). Devuelve None si
    no encuentra el header o si las llaves no balancean.
    """
    m = _THEMES_HEADER.search(text)
    if m is None:
        return None
    start = m.start()
    i = m.end()
    depth = 1
    in_string = False
    while i < len(text) and depth > 0:
        c = text[i]
        if in_string:
            if c == "\\" and i + 1 < len(text):
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return (start, i) if depth == 0 else None


def render_themes_block(themes: list[ZellijTheme]) -> str:
    """Emite KDL limpio del bloque themes { ... }. Slots como `name "value"`."""
    lines = ["themes {"]
    for t in themes:
        lines.append(f"    {t.name} {{")
        for color in t.colors:
            lines.append(f'        {color.name} "{color.value}"')
        lines.append("    }")
    lines.append("}")
    return "\n".join(lines)


def save_user_themes(
    config_path: Path,
    themes: list[ZellijTheme],
    *,
    backup: bool = True,
) -> Path | None:
    """Sustituye (o anade) el bloque `themes { ... }` en config.kdl.

    El resto del archivo se preserva. Si `themes` esta vacio y existia un
    bloque, se elimina entero. Crea backup antes de escribir.

    Limitacion: comentarios dentro del bloque themes se pierden (mismo
    motivo que en otros editores: re-emision desde el modelo).
    """
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    backup_path = make_backup(config_path) if backup and config_path.exists() else None
    range_ = find_themes_block(text)

    if not themes:
        if range_ is None:
            new = text
        else:
            start, end = range_
            new = text[:start] + text[end:]
            new = re.sub(r"\n{3,}", "\n\n", new)
    else:
        block = render_themes_block(themes)
        if range_ is None:
            sep = "" if text.endswith("\n") or not text else "\n"
            new = f"{text}{sep}{block}\n"
        else:
            start, end = range_
            new = text[:start] + block + text[end:]

    if new != text:
        write_atomic(config_path, new)
    return backup_path


def upsert_user_theme(
    config_path: Path, theme: ZellijTheme, *, backup: bool = True
) -> Path | None:
    """Crea o reemplaza el tema (por nombre) en el bloque themes."""
    current = list_user_themes(config_path)
    by_name: dict[str, ZellijTheme] = {t.name: t for t in current}
    by_name[theme.name] = theme
    return save_user_themes(config_path, list(by_name.values()), backup=backup)


def delete_user_theme(
    config_path: Path, name: str, *, backup: bool = True
) -> Path | None:
    """Borra un tema del bloque themes. No es error si no existe."""
    current = list_user_themes(config_path)
    new_list = [t for t in current if t.name != name]
    if len(new_list) == len(current):
        return None
    return save_user_themes(config_path, new_list, backup=backup)


def clone_theme(
    config_path: Path,
    src_name: str,
    dst_name: str,
    *,
    backup: bool = True,
) -> Path | None:
    """Clona un tema existente bajo dst_name.

    Si src_name es un user theme, copia sus colores. Si es built-in (no
    tenemos los colores), crea con LEGACY_SLOTS = "#000000" para que el
    usuario los rellene en el editor.
    """
    if not is_valid_theme_name(dst_name):
        raise ValueError(f"Nombre invalido: {dst_name!r}")
    current = list_user_themes(config_path)
    by_name = {t.name: t for t in current}
    if dst_name in by_name:
        raise ValueError(f"Ya existe un user theme '{dst_name}'")

    src_user = by_name.get(src_name)
    if src_user is not None:
        colors = list(src_user.colors)
    else:
        colors = [ZellijColor(name=s, value="#000000") for s in LEGACY_SLOTS]

    new_theme = ZellijTheme(name=dst_name, source="user", colors=colors)
    return upsert_user_theme(config_path, new_theme, backup=backup)


# ---------- mapping Zellij -> Textual ----------

TEXTUAL_FALLBACK = "textual-dark"

# Curado manualmente: cada tema Zellij apunta a un tema de Textual
# disponible. Cubre los 33 temas built-in. Para temas user-defined o
# nombres desconocidos se usa `TEXTUAL_FALLBACK`.
ZELLIJ_TO_TEXTUAL: dict[str, str] = {
    # Match exacto
    "catppuccin-frappe": "catppuccin-frappe",
    "catppuccin-macchiato": "catppuccin-macchiato",
    "catppuccin-mocha": "catppuccin-mocha",
    "catppuccin-latte": "catppuccin-latte",
    "dracula": "dracula",
    "tokyo-night": "tokyo-night",
    "solarized-dark": "solarized-dark",
    "solarized-light": "solarized-light",
    # Curado: dark
    "ao": "nord",
    "ayu-dark": "ansi-dark",
    "ayu-mirage": "ansi-dark",
    "cyber-noir": "nord",
    "default": "textual-dark",
    "everforest-dark": "nord",
    "gruber-darker": "flexoki",
    "kanagawa": "gruvbox",
    "lucario": "ansi-dark",
    "menace": "textual-dark",
    "night-owl": "ansi-dark",
    "nightfox": "tokyo-night",
    "onedark": "atom-one-dark",
    "one-half-dark": "atom-one-dark",
    "retro-wave": "textual-dark",
    "terafox": "nord",
    "tokyo-night-dark": "tokyo-night",
    "tokyo-night-storm": "tokyo-night",
    "vesper": "flexoki",
    # Curado: light
    "ayu-light": "rose-pine-dawn",
    "dayfox": "monokai",
    "everforest-light": "rose-pine-dawn",
    "gruvbox-light": "gruvbox",
    "iceberg-light": "rose-pine-moon",
    "tokyo-night-light": "rose-pine",
}


def textual_theme_for(zellij_name: str | None) -> str:
    """Devuelve el tema de Textual que mejor matchea el tema de Zellij dado.

    Para temas user-defined o nombres no mapeados, devuelve TEXTUAL_FALLBACK.
    """
    if not zellij_name:
        return TEXTUAL_FALLBACK
    return ZELLIJ_TO_TEXTUAL.get(zellij_name, TEXTUAL_FALLBACK)


def default_legacy_slots() -> list[ZellijColor]:
    """11 slots con valores neutros para crear un tema nuevo desde cero."""
    defaults = {
        "fg": "#cccccc",
        "bg": "#1e1e1e",
        "black": "#000000",
        "red": "#cc0000",
        "green": "#00cc00",
        "yellow": "#cccc00",
        "blue": "#0066cc",
        "magenta": "#cc00cc",
        "cyan": "#00cccc",
        "white": "#ffffff",
        "orange": "#ff8800",
    }
    return [ZellijColor(name=s, value=defaults[s]) for s in LEGACY_SLOTS]
