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

from ztc.services import toml_io
from ztc.services.colors import CanonicalSlot
from ztc.services.fonts import resolve_font_faces
from ztc.services.terminals import default_import_theme_file
from ztc.services.terminals.settings import (
    SETTINGS,
    CanonicalSetting,
    coerce_setting_value,
    validate_setting_value,
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

# Mapeo de cada setting canonico al path TOML donde Alacritty lo guarda.
# Ej. `window.padding.x` -> doc["window"]["padding"]["x"].
_CANONICAL_TO_ALACRITTY_SETTING: dict[str, tuple[str, ...]] = {
    "window.columns": ("window", "dimensions", "columns"),
    "window.lines": ("window", "dimensions", "lines"),
    "window.padding.x": ("window", "padding", "x"),
    "window.padding.y": ("window", "padding", "y"),
    "window.opacity": ("window", "opacity"),
    "font.size": ("font", "size"),
    "font.family": ("font", "normal", "family"),
    "cursor.shape": ("cursor", "style", "shape"),
}


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

    def reload_after_save(self, doc: TOMLDocument, path: Path) -> bool:
        return True

    def manual_reload_hint(self) -> str | None:
        return None

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
        return default_import_theme_file(self, doc, source_path)

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

    # ---------- settings (window, font, cursor) ----------

    def supported_settings(self) -> list[CanonicalSetting]:
        return [SETTINGS[name] for name in _CANONICAL_TO_ALACRITTY_SETTING]

    def read_setting(
        self, doc: TOMLDocument, setting: CanonicalSetting
    ) -> object | None:
        path = _CANONICAL_TO_ALACRITTY_SETTING.get(setting.name)
        if path is None:
            return None
        raw = _read_path(doc, path)
        if raw is None:
            return None
        return coerce_setting_value(setting, raw)

    def write_setting(
        self, doc: TOMLDocument, setting: CanonicalSetting, value: object
    ) -> None:
        if not validate_setting_value(setting, value):
            raise ValueError(
                f"Invalid value for {setting.name!r} ({setting.kind.value}): {value!r}"
            )
        path = _CANONICAL_TO_ALACRITTY_SETTING.get(setting.name)
        if path is None:
            raise KeyError(f"Setting {setting.name!r} not supported by Alacritty")
        if setting.name == "font.family" and isinstance(value, str):
            _write_alacritty_font_family(doc, value)
            _mark_setting_changed(doc, setting.name)
            return
        _write_path(doc, path, value)
        _mark_setting_changed(doc, setting.name)

    def delete_setting(
        self, doc: TOMLDocument, setting: CanonicalSetting
    ) -> bool:
        if setting.name == "font.family":
            deleted = _delete_alacritty_font_family(doc)
            if deleted:
                _mark_setting_changed(doc, setting.name)
            return deleted
        path = _CANONICAL_TO_ALACRITTY_SETTING.get(setting.name)
        if path is None:
            return False
        deleted = _delete_path(doc, path)
        if deleted:
            _mark_setting_changed(doc, setting.name)
        return deleted


# ---------- helpers TOML por path ----------


def _read_path(doc: TOMLDocument, path: tuple[str, ...]) -> object | None:
    """Navega `doc[path[0]][path[1]]...` y devuelve el leaf, o None si
    falta cualquier nivel. Funciona indistinto con tablas inline
    (`padding = { x = 8 }`) y dotted (`[window.padding] x = 8`) — tomlkit
    expone ambas igual al leer."""
    current: object = doc
    for key in path:
        if not isinstance(current, dict):
            return None
        if key not in current:
            return None
        current = current[key]
    return current


def _mark_setting_changed(doc: TOMLDocument, setting_name: str) -> None:
    changed = getattr(doc, "changed_settings", None)
    if changed is None:
        changed = set()
        doc.changed_settings = changed
    changed.add(setting_name)


def _write_alacritty_font_family(doc: TOMLDocument, family: str) -> None:
    faces = resolve_font_faces(family)
    by_face = {
        "normal": faces.normal,
        "bold": faces.bold,
        "italic": faces.italic,
        "bold_italic": faces.bold_italic,
    }
    for name, face in by_face.items():
        _write_path(doc, ("font", name, "family"), face.family)
        _write_path(doc, ("font", name, "style"), face.style)


def _delete_alacritty_font_family(doc: TOMLDocument) -> bool:
    deleted = False
    for face_name in ("normal", "bold", "italic", "bold_italic"):
        deleted = _delete_path(doc, ("font", face_name, "family")) or deleted
        deleted = _delete_path(doc, ("font", face_name, "style")) or deleted
    return deleted


def _write_path(doc: TOMLDocument, path: tuple[str, ...], value: object) -> None:
    """Escribe value en `doc[path[0]][path[1]]...`, creando tablas
    intermedias si hacen falta. Preserva forma existente (inline vs
    dotted) si ya esta declarada."""
    *parents, leaf = path
    current: dict = doc
    for key in parents:
        if key not in current:
            current[key] = tomlkit.table()
        current = current[key]  # type: ignore[assignment]
    current[leaf] = value


def _delete_path(doc: TOMLDocument, path: tuple[str, ...]) -> bool:
    """Borra `doc[path[0]][path[1]]...[leaf]` y, si quedan tablas
    intermedias vacias, las borra tambien. Devuelve True si el leaf
    existia."""
    *parents, leaf = path
    chain: list[tuple[dict, str]] = []
    current: object = doc
    for key in parents:
        if not isinstance(current, dict) or key not in current:
            return False
        chain.append((current, key))  # type: ignore[arg-type]
        current = current[key]
    if not isinstance(current, dict) or leaf not in current:
        return False
    del current[leaf]
    # Limpiar tablas vacias hacia arriba.
    while chain:
        parent, key = chain.pop()
        if isinstance(parent[key], dict) and len(parent[key]) == 0:
            del parent[key]
        else:
            break
    return True
