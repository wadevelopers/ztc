"""Registry de backends de terminal.

En Fase A solo hay Alacritty. Fase C agrega kitty. Ghostty queda
diferido (Fase D futura).
"""

from __future__ import annotations

from term_config_tui.services.terminals import TerminalBackend
from term_config_tui.services.terminals.alacritty import AlacrittyBackend
from term_config_tui.services.terminals.kitty import KittyBackend

_BACKENDS: dict[str, type[TerminalBackend]] = {
    "alacritty": AlacrittyBackend,
    "kitty": KittyBackend,
}


def get_backend(kind: str) -> TerminalBackend | None:
    """Devuelve una instancia nueva del backend, o None si no esta registrado."""
    cls = _BACKENDS.get(kind)
    return cls() if cls else None


def is_backend_available(kind: str) -> bool:
    return kind in _BACKENDS


def available_kinds() -> list[str]:
    return sorted(_BACKENDS.keys())
