"""Wrappers de escritura sobre el config.kdl de Zellij + helpers de
layouts y setup.

`read_active_theme` se importo a `zellij_themes.config` (shared) y se
re-exporta acá para mantener los call sites existentes.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from zellij_themes.config import read_active_theme  # re-export

from ztc.models.layout import Layout
from ztc.services import kdl_io
from ztc.services.atomic import write_atomic
from ztc.services.backups import make_backup

# Linea no comentada que empieza por `theme "..."`. Acepta indentacion vacia.
# Se requiere ausencia de `//` antes de `theme` en la misma linea.
_THEME_LINE = re.compile(
    r"""^(?P<prefix>[ \t]*)theme[ \t]+"(?P<name>[^"]*)"[ \t]*$""",
    re.MULTILINE,
)

_VALID_THEME_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")


def _is_commented(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("//")


def set_active_theme(
    config_path: Path,
    theme: str,
    *,
    backup: bool = True,
) -> Path | None:
    """Cambia (o inserta) la directiva `theme "..."` preservando el resto del archivo.

    - Reemplaza solo la primera linea no comentada que coincida con `theme "..."`.
    - Si no hay ninguna, anade `theme "<name>"` al final.
    - Crea backup antes de escribir si `backup=True`.
    Devuelve la ruta del backup creado o None.
    """
    if not _VALID_THEME_NAME.match(theme):
        raise ValueError(f"Invalid theme name: {theme!r}")

    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""

    backup_path: Path | None = None
    if backup and config_path.exists():
        backup_path = make_backup(config_path)

    new_text, replaced = _replace_first_uncommented_theme(text, theme)
    if not replaced:
        sep = "" if text.endswith("\n") or text == "" else "\n"
        new_text = f"{text}{sep}theme \"{theme}\"\n"

    write_atomic(config_path, new_text)
    return backup_path


def _replace_first_uncommented_theme(text: str, new_theme: str) -> tuple[str, bool]:
    out: list[str] = []
    cursor = 0
    replaced = False
    for match in _THEME_LINE.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end_idx = text.find("\n", match.end())
        line_end = line_end_idx if line_end_idx != -1 else len(text)
        line = text[line_start:line_end]
        if _is_commented(line):
            continue
        out.append(text[cursor:line_start])
        prefix = match.group("prefix")
        out.append(f'{prefix}theme "{new_theme}"')
        cursor = line_end
        replaced = True
        break
    out.append(text[cursor:])
    return "".join(out), replaced


def list_layouts(layouts_dir: Path) -> list[Layout]:
    """Devuelve los layouts en el directorio (no recursivo). Ordenados por nombre."""
    if not layouts_dir.exists():
        return []
    items: list[Layout] = []
    for path in sorted(layouts_dir.glob("*.kdl")):
        try:
            layout = kdl_io.load_layout(path)
        except Exception:
            layout = Layout(name=path.stem, path=path)
        items.append(layout)
    return items


def zellij_setup_check(timeout: float = 10.0) -> tuple[bool, str]:
    """Ejecuta `zellij setup --check`. Devuelve (ok, output_combinado).

    Si zellij no esta instalado devuelve (False, mensaje).
    """
    if shutil.which("zellij") is None:
        return False, "zellij no esta instalado"
    try:
        proc = subprocess.run(
            ["zellij", "setup", "--check"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "zellij setup --check excedio el timeout"
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output


__all__ = [
    "list_layouts",
    "read_active_theme",
    "set_active_theme",
    "zellij_setup_check",
]
