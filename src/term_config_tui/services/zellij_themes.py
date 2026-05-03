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

# Excluimos 'ansi' del listing y registro porque usa indices de paleta del
# terminal (0..15) en vez de RGB. No podemos construir un Textual Theme
# desde el sin saber la paleta del terminal del usuario.
_EXCLUDED_BUILTINS = frozenset({"ansi"})


def builtin_theme_names() -> tuple[str, ...]:
    """Nombres de los temas built-in de Zellij, derivados de los .kdl
    vendorizados en src/term_config_tui/assets/zellij_themes/.

    Excluye 'ansi' (formato palette-index, sin RGB).
    """
    from term_config_tui.services import zellij_theme_assets as zta

    names = [n for n in zta.list_bundled_theme_names() if n not in _EXCLUDED_BUILTINS]
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
        from term_config_tui.services import zellij_theme_assets as zta

        derived = zta.derive_legacy_slots_from_bundled(src_name)
        if derived is None:
            colors = [ZellijColor(name=s, value="#000000") for s in LEGACY_SLOTS]
        else:
            colors = [ZellijColor(name=s, value=derived[s]) for s in LEGACY_SLOTS]

    new_theme = ZellijTheme(name=dst_name, source="user", colors=colors)
    return upsert_user_theme(config_path, new_theme, backup=backup)


# Fallback cuando el tema activo de Zellij no esta registrado como Textual.
TEXTUAL_FALLBACK = "textual-dark"


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
