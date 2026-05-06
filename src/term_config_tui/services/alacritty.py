"""Servicio para leer/escribir slots de color en alacritty.toml."""

from __future__ import annotations

from pathlib import Path

import tomlkit
from tomlkit.items import Array
from tomlkit.toml_document import TOMLDocument

from term_config_tui.services import toml_io
from term_config_tui.services.colors import is_valid_hex, normalize_hex

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
