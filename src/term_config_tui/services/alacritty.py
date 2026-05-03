"""Servicio para leer/escribir slots de color en alacritty.toml."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import tomlkit
from tomlkit.items import Array
from tomlkit.toml_document import TOMLDocument

from term_config_tui.services import toml_io

# Estructura conocida de Alacritty.
SLOT_GROUPS: dict[str, tuple[str, ...]] = {
    "primary": ("background", "foreground"),
    "normal": ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"),
    "bright": ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"),
    "selection": ("text", "background"),
    "cursor": ("text", "cursor"),
}

# Orden estable de los slots para iterar siempre igual.
KNOWN_SLOTS: list[tuple[str, str]] = [
    (group, name) for group, names in SLOT_GROUPS.items() for name in names
]

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


@dataclass(frozen=True)
class Warning:
    slot: tuple[str, str] | None
    message: str


def is_valid_hex(value: str) -> bool:
    return bool(_HEX.match(value.strip()))


def normalize_hex(value: str) -> str:
    """Devuelve el valor en minusculas con #. Asume que ya es hex valido."""
    return "#" + value.strip().lstrip("#").lower()


def read_slot(doc: TOMLDocument, group: str, name: str) -> str | None:
    colors = doc.get("colors")
    if not colors:
        return None
    group_table = colors.get(group)
    if not group_table:
        return None
    raw = group_table.get(name)
    if raw is None:
        return None
    return str(raw)


def write_slot(doc: TOMLDocument, group: str, name: str, value: str) -> None:
    """Asigna el valor en doc.colors.<group>.<name>, creando tablas si faltan."""
    if "colors" not in doc:
        doc["colors"] = tomlkit.table()
    colors = doc["colors"]
    if group not in colors:
        colors[group] = tomlkit.table()
    colors[group][name] = value  # type: ignore[index]


def delete_slot(doc: TOMLDocument, group: str, name: str) -> bool:
    """Borra el slot del TOML. Devuelve True si existia.

    Si el grupo queda vacio tras borrar, tambien se elimina la tabla del
    grupo (y la tabla `colors` si queda sin nada).
    """
    colors = doc.get("colors")
    if not colors:
        return False
    group_table = colors.get(group)
    if not group_table or name not in group_table:
        return False
    del group_table[name]
    if len(group_table) == 0:
        del colors[group]
    if len(colors) == 0:
        del doc["colors"]
    return True


def read_all_slots(doc: TOMLDocument) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for group, name in KNOWN_SLOTS:
        value = read_slot(doc, group, name)
        if value is not None:
            out[(group, name)] = value
    return out


def import_theme_file(doc: TOMLDocument, source_path: Path) -> int:
    """Copia los slots conocidos desde otro alacritty.toml al doc actual.

    Devuelve cuantos slots se sobrescribieron. No toca otras secciones.
    Ignora valores que no sean hex validos.
    """
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    other = toml_io.load_toml(source_path)
    count = 0
    for group, name in KNOWN_SLOTS:
        value = read_slot(other, group, name)
        if value is None:
            continue
        if not is_valid_hex(value):
            continue
        write_slot(doc, group, name, normalize_hex(value))
        count += 1
    return count


def get_imports(doc: TOMLDocument) -> list[str]:
    raw = doc.get("import")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return []


def add_import(doc: TOMLDocument, path: str) -> bool:
    """Anade una entrada al array `import` si no existe ya. Devuelve True si la anadio."""
    current = get_imports(doc)
    if path in current:
        return False
    if "import" not in doc:
        arr = tomlkit.array()
        arr.append(path)
        doc["import"] = arr
        return True
    raw = doc["import"]
    if isinstance(raw, Array):
        raw.append(path)
        return True
    # Reemplazo defensivo si el campo existe con un tipo inesperado.
    arr = tomlkit.array()
    for item in current:
        arr.append(item)
    arr.append(path)
    doc["import"] = arr
    return True


# ---------- contraste WCAG ----------


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    if not is_valid_hex(value):
        return None
    s = value.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) == 8:  # ignora alpha
        s = s[:6]
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _rel_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(a: str, b: str) -> float | None:
    """Ratio WCAG entre dos hex. Devuelve None si alguno es invalido. Rango 1..21."""
    rgb_a = _hex_to_rgb(a)
    rgb_b = _hex_to_rgb(b)
    if rgb_a is None or rgb_b is None:
        return None
    la = _rel_luminance(rgb_a)
    lb = _rel_luminance(rgb_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def compute_warnings(
    doc: TOMLDocument, *, zellij_bg: str | None = None
) -> list[Warning]:
    """Detecta combinaciones problematicas. Heuristicas conservadoras:

    - background ~ normal.black: ratio < 1.5 -> aviso (puede confundir terminal apps).
    - background ~ zellij_bg: ratio < 1.3 -> aviso (UI de Zellij invisible).
    - selection.background ~ primary.background: ratio < 1.3 -> aviso.
    - cursor.cursor ~ primary.background: ratio < 2.0 -> aviso.
    """
    warnings: list[Warning] = []

    bg = read_slot(doc, "primary", "background")
    fg = read_slot(doc, "primary", "foreground")
    black = read_slot(doc, "normal", "black")
    sel_bg = read_slot(doc, "selection", "background")
    cur = read_slot(doc, "cursor", "cursor")

    if bg and fg:
        ratio = contrast_ratio(bg, fg)
        if ratio is not None and ratio < 4.5:
            warnings.append(
                Warning(
                    slot=("primary", "foreground"),
                    message=(
                        f"primary.foreground vs primary.background: contraste {ratio:.1f} "
                        "(WCAG recomienda >= 4.5 para texto)."
                    ),
                )
            )

    if bg and black:
        ratio = contrast_ratio(bg, black)
        if ratio is not None and ratio < 1.5:
            warnings.append(
                Warning(
                    slot=("normal", "black"),
                    message=(
                        f"primary.background y normal.black estan muy cerca (ratio {ratio:.2f}); "
                        "apps que usen 'black' sobre el fondo seran invisibles."
                    ),
                )
            )

    if bg and zellij_bg:
        ratio = contrast_ratio(bg, zellij_bg)
        if ratio is not None and ratio < 1.3:
            warnings.append(
                Warning(
                    slot=None,
                    message=(
                        f"alacritty primary.background ({bg}) vs zellij bg ({zellij_bg}): "
                        f"ratio {ratio:.2f}. Las barras de Zellij seran dificiles de ver."
                    ),
                )
            )

    if bg and sel_bg:
        ratio = contrast_ratio(bg, sel_bg)
        if ratio is not None and ratio < 1.3:
            warnings.append(
                Warning(
                    slot=("selection", "background"),
                    message=(
                        f"selection.background tiene poco contraste con el fondo "
                        f"(ratio {ratio:.2f}); la seleccion no se vera."
                    ),
                )
            )

    if bg and cur:
        ratio = contrast_ratio(bg, cur)
        if ratio is not None and ratio < 2.0:
            warnings.append(
                Warning(
                    slot=("cursor", "cursor"),
                    message=(
                        f"cursor.cursor tiene poco contraste con el fondo "
                        f"(ratio {ratio:.2f}); el cursor sera dificil de localizar."
                    ),
                )
            )

    return warnings
