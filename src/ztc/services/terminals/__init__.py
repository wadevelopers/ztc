"""Abstraccion de backends de terminal: Protocol comun y tipos
canonicos. Cada backend concreto vive en `services/terminals/<kind>.py`."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from zellij_themes.colors import CanonicalSlot

# Doc opaco que cada backend tipa internamente (TOMLDocument para
# alacritty, lista de lineas para kitty/ghostty).
BackendDoc = Any


@runtime_checkable
class TerminalBackend(Protocol):
    """Interfaz comun a todos los backends de terminal.

    Un backend lee/escribe slots canonicos `(group, name)` mapeandolos
    a la nomenclatura propia de su archivo de config.
    `import_theme_file` no esta en la Protocol — es capability de
    Alacritty (importar otro `alacritty.toml`); el editor lo invoca
    via `isinstance(backend, AlacrittyBackend)` cuando aplica.
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


__all__ = ["BackendDoc", "CanonicalSlot", "TerminalBackend"]
