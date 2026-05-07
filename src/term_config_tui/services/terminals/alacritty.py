"""Backend de Alacritty: I/O sobre `alacritty.toml`.

Slots canonicos `(group, name)` se mapean 1:1 a `[colors.<group>].<name>`
en el TOML, ya que el vocabulario canonico se modela sobre la
estructura de Alacritty.
"""

from __future__ import annotations

from pathlib import Path

import tomlkit
from tomlkit.items import Array
from tomlkit.toml_document import TOMLDocument

from term_config_tui.services import toml_io
from zellij_themes.colors import (
    CanonicalSlot,
    is_valid_hex,
    normalize_hex,
)

# Estructura conocida de Alacritty (define el vocabulario canonico).
SLOT_GROUPS: dict[str, tuple[str, ...]] = {
    "primary": ("background", "foreground"),
    "normal": ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"),
    "bright": ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"),
    "selection": ("text", "background"),
    "cursor": ("text", "cursor"),
}

KNOWN_SLOTS: list[CanonicalSlot] = [
    (group, name) for group, names in SLOT_GROUPS.items() for name in names
]


class AlacrittyBackend:
    """Backend para `alacritty.toml`."""

    kind: str = "alacritty"
    display_name: str = "Alacritty"

    def default_config_path(self) -> Path:
        return Path.home() / ".config" / "alacritty" / "alacritty.toml"

    def supported_slots(self) -> list[CanonicalSlot]:
        return list(KNOWN_SLOTS)

    def load(self, path: Path) -> TOMLDocument:
        return toml_io.load_toml(path)

    def save(self, doc: TOMLDocument, path: Path) -> Path | None:
        return toml_io.dump_toml(doc, path)

    def read_slot(self, doc: TOMLDocument, slot: CanonicalSlot) -> str | None:
        group, name = slot
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

    def write_slot(
        self, doc: TOMLDocument, slot: CanonicalSlot, value: str
    ) -> None:
        group, name = slot
        if "colors" not in doc:
            doc["colors"] = tomlkit.table()
        colors = doc["colors"]
        if group not in colors:
            colors[group] = tomlkit.table()
        colors[group][name] = value  # type: ignore[index]

    def delete_slot(self, doc: TOMLDocument, slot: CanonicalSlot) -> bool:
        group, name = slot
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

    # ---------- capabilities especificas de Alacritty ----------

    def read_all_slots(self, doc: TOMLDocument) -> dict[CanonicalSlot, str]:
        out: dict[CanonicalSlot, str] = {}
        for slot in KNOWN_SLOTS:
            value = self.read_slot(doc, slot)
            if value is not None:
                out[slot] = value
        return out

    def import_theme_file(self, doc: TOMLDocument, source_path: Path) -> int:
        """Copia los slots conocidos desde otro alacritty.toml al doc actual.

        Devuelve cuantos slots se sobrescribieron. No toca otras secciones.
        Ignora valores que no sean hex validos. Capability solo de
        Alacritty (no esta en la Protocol comun).
        """
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        other = toml_io.load_toml(source_path)
        count = 0
        for slot in KNOWN_SLOTS:
            value = self.read_slot(other, slot)
            if value is None or not is_valid_hex(value):
                continue
            self.write_slot(doc, slot, normalize_hex(value))
            count += 1
        return count

    def get_imports(self, doc: TOMLDocument) -> list[str]:
        raw = doc.get("import")
        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(x) for x in raw]
        return []

    def add_import(self, doc: TOMLDocument, path: str) -> bool:
        """Anade una entrada al array `import` si no existe ya."""
        current = self.get_imports(doc)
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
        arr = tomlkit.array()
        for item in current:
            arr.append(item)
        arr.append(path)
        doc["import"] = arr
        return True
