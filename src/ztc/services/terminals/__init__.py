"""Abstraccion de backends de terminal: Protocol comun y tipos
canonicos. Cada backend concreto vive en `services/terminals/<kind>.py`."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ztc.services.colors import CanonicalSlot, is_valid_hex, normalize_hex
from ztc.services.terminals.settings import CanonicalSetting

# Doc opaco que cada backend tipa internamente (TOMLDocument para
# alacritty, lista de lineas para kitty/ghostty).
BackendDoc = Any


@runtime_checkable
class TerminalBackend(Protocol):
    """Interfaz comun a todos los backends de terminal.

    Un backend lee/escribe slots canonicos `(group, name)` y settings
    canonicos mapeandolos a la nomenclatura propia de su archivo de
    config. Tambien soporta `import_theme_file` para copiar slots desde
    otro archivo del mismo formato, y expone capacidades runtime para
    aplicar o explicar la recarga post-save.
    """

    kind: str
    display_name: str

    def default_config_path(self) -> Path: ...

    def load(self, path: Path) -> BackendDoc: ...

    def save(self, doc: BackendDoc, path: Path) -> Path | None:
        """Devuelve el path del backup creado, o None si no habia
        archivo previo (no hay backup que crear)."""
        ...

    def read_slot(
        self, doc: BackendDoc, slot: CanonicalSlot
    ) -> str | None: ...

    def write_slot(
        self, doc: BackendDoc, slot: CanonicalSlot, value: str
    ) -> None: ...

    def delete_slot(self, doc: BackendDoc, slot: CanonicalSlot) -> bool: ...

    def supported_slots(self) -> list[CanonicalSlot]: ...

    def import_theme_file(self, doc: BackendDoc, source_path: Path) -> int:
        """Copia los slots conocidos desde otro archivo del mismo formato
        (mismo backend) al doc actual. Devuelve cuantos slots se
        sobrescribieron. No toca otras secciones del archivo. Ignora
        valores que no sean hex validos. Levanta `FileNotFoundError`
        si `source_path` no existe."""
        ...

    # ---------- settings (padding, opacity, font, cursor shape, ...) ----------

    def read_setting(
        self, doc: BackendDoc, setting: CanonicalSetting
    ) -> object | None:
        """Devuelve el valor actual del setting (tipo segun setting.kind),
        o None si no esta definido en el archivo."""
        ...

    def write_setting(
        self, doc: BackendDoc, setting: CanonicalSetting, value: object
    ) -> None:
        """Escribe value en el archivo con el formato propio del backend.

        Antes de escribir, llama a `validate_setting_value(setting, value)`
        y levanta `ValueError` si el valor no es valido (rango, kind,
        enum). Asi la validacion vive en un solo lugar (el catalogo) y
        no depende solo de la UI — un caller programatico tampoco puede
        meter basura en el archivo.
        """
        ...

    def delete_setting(
        self, doc: BackendDoc, setting: CanonicalSetting
    ) -> bool:
        """Elimina la entrada del archivo. Devuelve True si existia."""
        ...

    def supported_settings(self) -> list[CanonicalSetting]:
        """Lista de settings que este backend soporta."""
        ...

    # ---------- runtime post-save ----------

    def reload_after_save(self) -> bool:
        """Intenta aplicar al terminal en ejecucion el archivo recien
        guardado.

        Devuelve True si la recarga funciono o si el backend recarga
        nativamente sin accion extra. Devuelve False si no se pudo
        recargar de forma programatica; el caller puede mostrar
        `manual_reload_hint()`.
        """
        ...

    def manual_reload_hint(self) -> str | None:
        """Instruccion visible al usuario cuando `reload_after_save()`
        devuelve False. None si el backend no requiere hint manual."""
        ...


# Filtro de extensiones que el FilePickerModal aplica al import de
# theme/settings, indexado por `backend.kind`. Single source of truth
# usado por color_editor y terminal_settings — sin duplicacion entre
# screens y sin meter el dato en el Protocol. Agregar un backend nuevo
# es una entrada acá.
IMPORT_EXTENSIONS_BY_KIND: dict[str, list[str]] = {
    "alacritty": [".toml"],
    "kitty": [".conf"],
}


def default_import_theme_file(
    backend: TerminalBackend, doc: BackendDoc, source_path: Path
) -> int:
    """Implementacion comun de `import_theme_file` para cualquier backend
    que se ajuste al patron canonico: leer otro archivo del mismo formato
    y copiar slots conocidos al doc actual.

    Cada backend concreto delega aca a menos que necesite logica propia
    (hoy ninguno la necesita). Centralizar previene divergencia silenciosa
    cuando se sume Ghostty u otro backend.

    Reglas:
    - `FileNotFoundError` si `source_path` no existe.
    - Itera sobre `backend.supported_slots()` (cada backend declara cuales).
    - Lee con `backend.read_slot`; ignora valores que no sean hex validos
      (named colors, oklch(...), etc. no se importan — `normalize_hex`
      tirarian sino).
    - Escribe con `backend.write_slot(doc, slot, normalize_hex(value))`.
    - Devuelve la cantidad de slots sobrescritos.
    """
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    other = backend.load(source_path)
    count = 0
    for slot in backend.supported_slots():
        value = backend.read_slot(other, slot)
        if value is None or not is_valid_hex(value):
            continue
        backend.write_slot(doc, slot, normalize_hex(value))
        count += 1
    return count


__all__ = [
    "IMPORT_EXTENSIONS_BY_KIND",
    "BackendDoc",
    "CanonicalSetting",
    "CanonicalSlot",
    "TerminalBackend",
    "default_import_theme_file",
]
