"""Backend de Alacritty: I/O sobre `alacritty.toml`.

Slots canonicos `(group, name)` se mapean 1:1 a `[colors.<group>].<name>`
en el TOML, ya que el vocabulario canonico se modela sobre la
estructura de Alacritty.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import tomlkit
from tomlkit.toml_document import TOMLDocument

from ztc.services import toml_io
from ztc.services.backups import make_backup
from ztc.services.colors import CanonicalSlot
from ztc.services.fonts import resolve_font_faces
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

_MANAGED_MARKER = "ztc-managed-manifest = true"
_GENERAL_IMPORT_MIN_VERSION = (0, 14, 0)

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

    # ---------- perfiles intercambiables (manifest + profile switching) ----------

    def is_managed_manifest(self, path: Path) -> bool:
        if not path.exists():
            return False
        text = path.read_text(encoding="utf-8")
        if _MANAGED_MARKER in text:
            return True
        doc = self.load(path)
        # Backward compatibility with old ZTC manifests. Do not write this
        # table anymore: Alacritty warns about unknown live config keys.
        ztc_section = doc.get("ztc")
        if not isinstance(ztc_section, dict):
            return False
        return bool(ztc_section.get("managed_manifest", False))

    def read_active_profile(self, manifest_path: Path) -> Path | None:
        if not self.is_managed_manifest(manifest_path):
            return None
        doc = self.load(manifest_path)
        imports = _read_imports(doc)
        if not imports:
            return None
        # tomlkit array se comporta como list pero no es list. Iteramos
        # para tolerar ambos tipos.
        try:
            raw = imports[0]
        except (IndexError, KeyError, TypeError):
            return None
        if not isinstance(raw, str):
            return None
        raw_path = Path(raw).expanduser()
        if raw_path.is_absolute():
            return raw_path
        return manifest_path.parent / raw_path

    def write_active_profile(
        self, manifest_path: Path, profile_path: Path
    ) -> None:
        doc = _build_manifest_doc(manifest_path, profile_path)
        toml_io.dump_toml(doc, manifest_path)

    def unmanage_manifest(
        self, manifest_path: Path, profile_doc: TOMLDocument
    ) -> Path | None:
        """Reescribe `manifest_path` con el contenido del `profile_doc`
        (perfil activo). Quita metadata legacy de ZTC si existe.
        Alacritty no tiene managed directives globales, asi que el
        resultado es el TOML del perfil escrito tal cual."""
        if not self.is_managed_manifest(manifest_path):
            return None
        backup = make_backup(manifest_path)
        # El profile_doc no deberia contener la seccion [ztc] (viene de
        # un perfil cargado, no del manifest). Defensivo: si la tiene, la
        # quitamos antes de escribir.
        if "ztc" in profile_doc:
            del profile_doc["ztc"]
        toml_io.dump_toml(profile_doc, manifest_path, backup=False)
        return backup

    def convert_to_manifest(
        self, manifest_path: Path, active_profile: Path
    ) -> Path | None:
        """Backup del archivo original + reescribe como manifest minimal
        apuntando a `active_profile`. El contenido viejo queda solo en
        el backup; no se duplica en `active_profile` (caller responsable
        de que exista)."""
        if not manifest_path.exists():
            raise FileNotFoundError(manifest_path)
        backup = make_backup(manifest_path)
        manifest_doc = _build_manifest_doc(manifest_path, active_profile)
        toml_io.dump_toml(manifest_doc, manifest_path, backup=False)
        return backup

    def reload_after_profile_switch(
        self, manifest_path: Path, new_profile_path: Path
    ) -> bool:
        # Live-reload nativo de Alacritty cubre el switch: el watchdog
        # detecta el cambio en el manifest, sigue el import y aplica.
        return True

    def reload_after_profile_save(
        self,
        profile_doc: TOMLDocument,
        profile_path: Path,
        manifest_path: Path,
    ) -> bool:
        # Live-reload nativo del manifest dispara al detectar cambio en
        # el archivo importado.
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


# ---------- helpers manifest Alacritty ----------


def _read_imports(doc: TOMLDocument) -> object | None:
    """Lee imports en formato Alacritty 0.13 y 0.14+.

    0.13 usa `import = [...]` en la raiz. 0.14 movio esa opcion a
    `[general] import = [...]`. Aceptamos ambos para poder leer manifests
    generados por versiones anteriores de ZTC o por otra version de
    Alacritty.
    """
    if _uses_general_import():
        return _read_general_imports(doc) or doc.get("import")
    return doc.get("import") or _read_general_imports(doc)


def _read_general_imports(doc: TOMLDocument) -> object | None:
    general = doc.get("general")
    if not isinstance(general, dict):
        return None
    return general.get("import")


def _build_manifest_doc(manifest_path: Path, profile_path: Path) -> TOMLDocument:
    doc = tomlkit.document()
    doc.add(tomlkit.comment(_MANAGED_MARKER))
    doc.add(tomlkit.nl())
    import_value = _profile_import_value(manifest_path, profile_path)
    if _uses_general_import():
        general = tomlkit.table()
        general["import"] = [import_value]
        doc["general"] = general
    else:
        doc["import"] = [import_value]
    return doc


def _profile_import_value(manifest_path: Path, profile_path: Path) -> str:
    return (
        profile_path.name
        if profile_path.parent == manifest_path.parent
        else str(profile_path)
    )


def _uses_general_import() -> bool:
    version = _detect_alacritty_version()
    if version is None:
        return True
    return version >= _GENERAL_IMPORT_MIN_VERSION


def _detect_alacritty_version() -> tuple[int, int, int] | None:
    try:
        proc = subprocess.run(
            ["alacritty", "--version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", proc.stdout + proc.stderr)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


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
