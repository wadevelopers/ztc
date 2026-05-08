"""Operaciones de escritura sobre el bloque `themes { ... }` en
config.kdl: save, upsert, delete, clone. Las funciones de **lectura**
viven en `ztc.zellij.user_themes` y `ztc.zellij.config`; los call sites
las importan directamente de alli en lugar de via re-export aca.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import kdl

from ztc.zellij.config import read_active_theme
from ztc.zellij.models import ZellijColor, ZellijTheme
from ztc.zellij.user_themes import (
    LEGACY_SLOTS,
    is_valid_theme_name,
    list_user_themes,
)

from ztc.services.atomic import write_atomic
from ztc.services.backups import make_backup

if TYPE_CHECKING:
    from ztc.services.terminals import TerminalBackend


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


# Slots requeridos por el parser de Zellij en cualquier componente que
# aparezca. Si falta uno, el parse falla entero (kdl/mod.rs:5158-1568).
# `background` es opcional (default a #000000 upstream).
_REQUIRED_RICH_SLOTS: tuple[str, ...] = (
    "base",
    "emphasis_0",
    "emphasis_1",
    "emphasis_2",
    "emphasis_3",
)

# Default para campos del Palette de Zellij que no almacenamos en legacy
# (purple, brown, gold, silver, pink, gray). Coincide con
# PaletteColor::default() = EightBit(0) = negro.
_PALETTE_DEFAULT_HEX = "#000000"

_DEFAULT_ORANGE_HEX = "#ff8800"


def derive_rich_block(
    palette: dict[str, str], *, orange_hint: str | None = None
) -> dict[str, dict[str, str]]:
    """Replica `From<Palette> for Styling` de Zellij (data.rs:1591) para
    los componentes que potencialmente emitimos. Devuelve un dict
    {componente: {slot: hex}} con los 6 slots por componente. El render
    elige cuáles efectivamente emite (segun RICH_SLOTS_TO_EXPOSE).

    `orange_hint`: la paleta legacy ya no incluye orange (no es de
    Alacritty). El llamador puede pasar el orange canonico (en el modelo
    rico vive en `text_unselected.emphasis_0`); si no, usamos un naranja
    neutro como semilla para temas frescos.

    Asume theme_hue=Dark (no almacenamos hue; en la rama IF Zellij usa
    Dark si no lo indicas). Para hue=Dark la regla es (fg, bg) ->
    (palette.white, palette.black).
    """
    p = lambda name: palette.get(name, _PALETTE_DEFAULT_HEX)  # noqa: E731
    fg = p("white")
    bg = p("black")
    orange = orange_hint or _DEFAULT_ORANGE_HEX
    cyan = p("cyan")
    green = p("green")
    magenta = p("magenta")
    red = p("red")
    blue = p("blue")
    black = p("black")
    white = p("white")
    palette_bg = p("bg")
    purple = _PALETTE_DEFAULT_HEX
    brown = _PALETTE_DEFAULT_HEX

    return {
        "text_unselected": {
            "base": fg,
            "background": bg,
            "emphasis_0": orange,
            "emphasis_1": cyan,
            "emphasis_2": green,
            "emphasis_3": magenta,
        },
        "text_selected": {
            "base": fg,
            "background": palette_bg,
            "emphasis_0": orange,
            "emphasis_1": cyan,
            "emphasis_2": green,
            "emphasis_3": magenta,
        },
        "ribbon_unselected": {
            "base": black,
            "background": p("fg"),
            "emphasis_0": red,
            "emphasis_1": white,
            "emphasis_2": blue,
            "emphasis_3": magenta,
        },
        "ribbon_selected": {
            "base": black,
            "background": green,
            "emphasis_0": red,
            "emphasis_1": orange,
            "emphasis_2": magenta,
            "emphasis_3": blue,
        },
        "frame_unselected": {
            # Sin derivacion upstream (frame_unselected es Option<> y From<Palette>
            # devuelve None). Tomamos palette.white como base para imitar el
            # blanco apagado que muestra Zellij con None en la mayoria de temas.
            "base": white,
            "background": _PALETTE_DEFAULT_HEX,
            "emphasis_0": orange,
            "emphasis_1": cyan,
            "emphasis_2": magenta,
            "emphasis_3": brown,
        },
        "frame_selected": {
            "base": green,
            "background": _PALETTE_DEFAULT_HEX,
            "emphasis_0": orange,
            "emphasis_1": cyan,
            "emphasis_2": magenta,
            "emphasis_3": brown,
        },
        "frame_highlight": {
            "base": orange,
            "background": _PALETTE_DEFAULT_HEX,
            "emphasis_0": magenta,
            "emphasis_1": purple,
            "emphasis_2": orange,
            "emphasis_3": orange,
        },
    }


def _slots_to_emit() -> dict[str, list[str]]:
    """Deriva de RICH_SLOTS_TO_EXPOSE qué emitir al .kdl: por cada
    componente con al menos un slot expuesto, los 5 obligatorios (base +
    emphasis_0..3) + `background` solo si está expuesto. Mantiene el
    orden en que cada componente aparece por primera vez en
    RICH_SLOTS_TO_EXPOSE."""
    exposed_by_component: dict[str, set[str]] = {}
    for component, slot in RICH_SLOTS_TO_EXPOSE:
        exposed_by_component.setdefault(component, set()).add(slot)
    out: dict[str, list[str]] = {}
    for component, slots in exposed_by_component.items():
        emitted = ["base"]
        if "background" in slots:
            emitted.append("background")
        emitted.extend(["emphasis_0", "emphasis_1", "emphasis_2", "emphasis_3"])
        out[component] = emitted
    return out


def render_themes_block(themes: list[ZellijTheme]) -> str:
    """Emite KDL del bloque themes { ... }.

    Por tema emite:
    - Paleta legacy (LEGACY_SLOTS, 10 colores espejo de Alacritty).
    - Solo los componentes ricos que tienen al menos un slot expuesto
      en RICH_SLOTS_TO_EXPOSE. Por cada uno emite los 5 slots
      obligatorios para Zellij (base + emphasis_0..3) y `background`
      solo si esta expuesto. Los slots editables vienen de
      raw_components (overrides del usuario o copiados del bundled);
      los obligatorios no expuestos se derivan de la paleta legacy.
    """
    components_to_emit = _slots_to_emit()
    lines = ["themes {"]
    for t in themes:
        lines.append(f"    {t.name} {{")
        for color in t.colors:
            if color.name not in LEGACY_SLOTS:
                continue
            lines.append(f'        {color.name} "{color.value}"')

        palette = {c.name: c.value for c in t.colors if c.name in LEGACY_SLOTS}
        overrides = _collect_rich_overrides(t, allowed=components_to_emit)
        orange_hint = overrides.get("text_unselected", {}).get("emphasis_0")
        derived = derive_rich_block(palette, orange_hint=orange_hint)
        for component, slots in components_to_emit.items():
            lines.append(f"        {component} {{")
            comp_overrides = overrides.get(component, {})
            for slot in slots:
                value = comp_overrides.get(slot, derived[component][slot])
                lines.append(f'            {slot} "{value}"')
            lines.append("        }")

        lines.append("    }")
    lines.append("}")
    return "\n".join(lines)


def _collect_rich_overrides(
    t: ZellijTheme, *, allowed: dict[str, list[str]]
) -> dict[str, dict[str, str]]:
    """Lee de raw_components solo los (componente, slot) que esten en
    `allowed` (los que se emiten al .kdl). Devuelve {componente: {slot:
    hex}} con valores normalizados."""
    out: dict[str, dict[str, str]] = {}
    for rc in t.raw_components:
        slots = allowed.get(rc.name)
        if slots is None:
            continue
        slot_set = set(slots)
        for child in rc.nodes:
            if child.name not in slot_set:
                continue
            value = _slot_value_to_hex(list(child.args))
            if value is not None:
                out.setdefault(rc.name, {})[child.name] = value
    return out


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
    backend: "TerminalBackend | None" = None,
    backend_path: Path | None = None,
    backup: bool = True,
) -> Path | None:
    """Clona un tema existente bajo dst_name.

    Fuente de los colores:
    - Si src_name es un user theme, copia sus colores tal cual.
    - Si es built-in vendorizado, deriva los slots legacy del .kdl.
    - Si no es ninguno, crea con LEGACY_SLOTS = "#000000".

    Si `backend` y `backend_path` se pasan Y src_name es el tema
    actualmente activo en config.kdl, los slots que existen en el
    archivo de la terminal (fg, bg, 8 normal) se overlayan SOBRE el
    resultado anterior. Esto preserva el estado real que el usuario
    esta viendo, incluyendo cualquier ajuste manual hecho en el editor
    de colores desde el ultimo apply.
    """
    if not is_valid_theme_name(dst_name):
        raise ValueError(f"Invalid name: {dst_name!r}")
    current = list_user_themes(config_path)
    by_name = {t.name: t for t in current}
    if dst_name in by_name:
        raise ValueError(f"User theme '{dst_name}' already exists")

    from ztc.zellij import theme_assets as zta

    src_user = by_name.get(src_name)
    if src_user is not None:
        colors = list(src_user.colors)
        raw_components = list(src_user.raw_components)
    else:
        derived = zta.derive_legacy_slots_from_bundled(src_name)
        if derived is None:
            colors = [ZellijColor(name=s, value="#000000") for s in LEGACY_SLOTS]
        else:
            colors = [ZellijColor(name=s, value=derived[s]) for s in LEGACY_SLOTS]
        raw_components = zta.load_bundled_raw_components(src_name)

    if backend is not None and backend_path is not None and backend_path.exists():
        active = read_active_theme(config_path)
        if active == src_name:
            overlay = _read_terminal_legacy_slots(backend, backend_path)
            if overlay:
                colors = _overlay_color_list(colors, overlay)

    new_theme = ZellijTheme(
        name=dst_name,
        source="user",
        colors=colors,
        raw_components=raw_components,
    )
    return upsert_user_theme(config_path, new_theme, backup=backup)


def _read_terminal_legacy_slots(
    backend: "TerminalBackend", backend_path: Path
) -> dict[str, str]:
    """Devuelve {legacy_slot: hex} con los valores actuales del archivo
    de la terminal, invirtiendo el mapping de theme_sync."""
    from ztc.services.colors import is_valid_hex, normalize_hex

    from ztc.services.theme_sync import _LEGACY_TO_CANONICAL

    doc = backend.load(backend_path)
    out: dict[str, str] = {}
    for legacy_name, destinations in _LEGACY_TO_CANONICAL.items():
        # Tomamos el primer destino que tenga valor en el doc.
        for slot in destinations:
            value = backend.read_slot(doc, slot)
            if value and is_valid_hex(value):
                out[legacy_name] = normalize_hex(value)
                break
    return out


def _overlay_color_list(
    colors: list[ZellijColor], overlay: dict[str, str]
) -> list[ZellijColor]:
    """Devuelve nueva lista con los slots de overlay sustituidos."""
    out: list[ZellijColor] = []
    seen = set()
    for c in colors:
        seen.add(c.name)
        if c.name in overlay:
            out.append(ZellijColor(name=c.name, value=overlay[c.name]))
        else:
            out.append(c)
    for name, value in overlay.items():
        if name not in seen:
            out.append(ZellijColor(name=name, value=value))
    return out


# Abreviaciones de slot solo para visualizacion. Al guardar al .kdl se
# usan los nombres canonicos de Zellij. El display es para que la fila
# entre en una columna compacta del editor/preview.
_SLOT_DISPLAY_ABBREV: dict[str, str] = {
    "background": "backgr",
    "emphasis_0": "emph_0",
    "emphasis_1": "emph_1",
    "emphasis_2": "emph_2",
}


def display_slot(component: str, slot: str) -> str:
    """Etiqueta visible para un (componente, slot) rico. Usa abreviaciones
    para los slots largos. NO se usa al renderizar al .kdl."""
    return f"{component}.{_SLOT_DISPLAY_ABBREV.get(slot, slot)}"


# Slots ricos expuestos en el editor + preview. 7 componentes x 2 slots
# principales (background, base) + 1 extra (text_unselected.emphasis_0,
# que es el "orange canonico" que Zellij usa internamente).
RICH_SLOTS_TO_EXPOSE: list[tuple[str, str]] = [
    ("text_unselected", "background"),
    ("text_unselected", "base"),
    ("text_unselected", "emphasis_0"),
    ("text_unselected", "emphasis_1"),
    ("text_unselected", "emphasis_2"),
    ("text_selected", "background"),
    ("text_selected", "base"),
    ("ribbon_unselected", "background"),
    ("ribbon_unselected", "base"),
    ("ribbon_unselected", "emphasis_0"),
    ("ribbon_selected", "background"),
    ("ribbon_selected", "base"),
    ("ribbon_selected", "emphasis_0"),
    ("frame_unselected", "base"),
    ("frame_selected", "base"),
    ("frame_highlight", "base"),
]


def _slot_value_to_hex(args: list) -> str | None:
    """Args de un kdl.Node de slot rico a hex. Acepta hex string o RGB."""
    if not args:
        return None
    if isinstance(args[0], str) and args[0].startswith("#"):
        return args[0].lower()
    nums = [int(a) for a in args[:3] if isinstance(a, (int, float))]
    if len(nums) < 3:
        return None
    return f"#{nums[0]:02x}{nums[1]:02x}{nums[2]:02x}"


def get_rich_slot(theme: ZellijTheme, component: str, slot: str) -> str | None:
    """Lee el valor hex de un slot rico del theme. None si no existe."""
    for rc in theme.raw_components:
        if rc.name != component:
            continue
        for child in rc.nodes:
            if child.name == slot:
                return _slot_value_to_hex(list(child.args))
    return None


def set_rich_slot(
    theme: ZellijTheme, component: str, slot: str, hex_value: str
) -> None:
    """Escribe (crea si hace falta) un slot rico en el theme."""
    rc = next((c for c in theme.raw_components if c.name == component), None)
    if rc is None:
        rc = kdl.parse(f'{component} {{\n    {slot} "{hex_value}"\n}}\n').nodes[0]
        theme.raw_components.append(rc)
        return
    slot_node = next((n for n in rc.nodes if n.name == slot), None)
    if slot_node is None:
        new_node = kdl.parse(f'{slot} "{hex_value}"\n').nodes[0]
        rc.nodes.append(new_node)
    else:
        slot_node.args = [hex_value]


def unset_rich_slot(theme: ZellijTheme, component: str, slot: str) -> None:
    """Elimina el slot rico del theme. Si la componente queda vacia, la
    elimina tambien."""
    rc = next((c for c in theme.raw_components if c.name == component), None)
    if rc is None:
        return
    rc.nodes = [n for n in rc.nodes if n.name != slot]
    if not rc.nodes:
        theme.raw_components.remove(rc)


def default_legacy_slots() -> list[ZellijColor]:
    """10 slots con valores neutros para crear un tema nuevo desde cero."""
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
    }
    return [ZellijColor(name=s, value=defaults[s]) for s in LEGACY_SLOTS]
