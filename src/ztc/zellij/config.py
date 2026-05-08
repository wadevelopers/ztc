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


def _is_commented(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("//")


def read_active_theme(config_path: Path) -> str | None:
    """Devuelve el nombre del tema activo (`theme "..."`), ignorando lineas comentadas.

    Si hay varias lineas no comentadas se devuelve la primera.
    Si no hay ninguna devuelve None.
    """
    if not config_path.exists():
        return None
    text = config_path.read_text(encoding="utf-8")
    for match in _THEME_LINE.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        line = text[line_start : line_end if line_end != -1 else len(text)]
        if _is_commented(line):
            continue
        return match.group("name")
    return None
