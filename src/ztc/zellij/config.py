"""Lectura del config.kdl de Zellij. Read-only — el shared package no
escribe configs (eso queda en las apps que sí editan)."""

from __future__ import annotations

import re
from pathlib import Path

# Linea no comentada que empieza por `theme "..."`. Acepta indentacion vacia.
# Se requiere ausencia de `//` antes de `theme` en la misma linea.
_THEME_LINE = re.compile(
    r"""^(?P<prefix>[ \t]*)theme[ \t]+"(?P<name>[^"]*)"[ \t]*$""",
    re.MULTILINE,
)

_ON_FORCE_CLOSE_LINE = re.compile(
    r"""^(?P<prefix>[ \t]*)on_force_close[ \t]+"(?P<value>detach|quit)"[ \t]*$""",
    re.MULTILINE,
)

_SESSION_SERIALIZATION_LINE = re.compile(
    r"""^(?P<prefix>[ \t]*)session_serialization[ \t]+(?P<value>true|false)[ \t]*$""",
    re.MULTILINE,
)

_SERIALIZE_PANE_VIEWPORT_LINE = re.compile(
    r"""^(?P<prefix>[ \t]*)serialize_pane_viewport[ \t]+(?P<value>true|false)[ \t]*$""",
    re.MULTILINE,
)


def _is_commented(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("//")


def _first_uncommented(text: str, pattern: re.Pattern[str]) -> re.Match[str] | None:
    """Devuelve el primer match no comentado del patron, o None."""
    for match in pattern.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        line = text[line_start : line_end if line_end != -1 else len(text)]
        if not _is_commented(line):
            return match
    return None


def read_active_theme(config_path: Path) -> str | None:
    """Devuelve el nombre del tema activo (`theme "..."`), ignorando lineas comentadas.

    Si hay varias lineas no comentadas se devuelve la primera.
    Si no hay ninguna devuelve None.
    """
    if not config_path.exists():
        return None
    text = config_path.read_text(encoding="utf-8")
    m = _first_uncommented(text, _THEME_LINE)
    return m.group("name") if m else None


def read_on_force_close(config_path: Path) -> str:
    """Devuelve el valor activo de `on_force_close` ("detach" o "quit").

    Si no esta seteado explicitamente, devuelve "detach" (default de Zellij).
    """
    if not config_path.exists():
        return "detach"
    text = config_path.read_text(encoding="utf-8")
    m = _first_uncommented(text, _ON_FORCE_CLOSE_LINE)
    return m.group("value") if m else "detach"


def check_session_serialization(config_path: Path) -> bool:
    """Devuelve True si session_serialization esta habilitado.

    El default de Zellij es true, asi que solo devuelve False si esta
    explicitamente seteado a false.
    """
    if not config_path.exists():
        return True
    text = config_path.read_text(encoding="utf-8")
    m = _first_uncommented(text, _SESSION_SERIALIZATION_LINE)
    if m is None:
        return True  # default es true
    return m.group("value") == "true"


def check_serialize_pane_viewport(config_path: Path) -> bool:
    """Devuelve True si serialize_pane_viewport esta habilitado.

    El default de Zellij es false, asi que devuelve False cuando esta
    ausente/comentado o explicitamente seteado a false.
    """
    if not config_path.exists():
        return False
    text = config_path.read_text(encoding="utf-8")
    m = _first_uncommented(text, _SERIALIZE_PANE_VIEWPORT_LINE)
    if m is None:
        return False  # default es false
    return m.group("value") == "true"
