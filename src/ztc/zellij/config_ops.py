"""Operaciones sobre el config.kdl de Zellij: escritura de
`set_active_theme`, lectura de layouts disponibles, verificacion de
instalacion. La lectura del tema activo (`read_active_theme`) vive en
`ztc.zellij.config`; los call sites la importan desde alli.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from ztc.models.layout import Layout
from ztc.services.atomic import write_atomic
from ztc.services.backups import make_backup
from ztc.zellij import layout_io

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

    new_text, replaced = _replace_first_uncommented(
        text, _THEME_LINE, f'theme "{theme}"'
    )
    if not replaced:
        sep = "" if text.endswith("\n") or text == "" else "\n"
        new_text = f"{text}{sep}theme \"{theme}\"\n"

    write_atomic(config_path, new_text)
    return backup_path


def set_on_force_close(
    config_path: Path,
    value: str,
    *,
    backup: bool = True,
) -> Path | None:
    """Escribe (o inserta) `on_force_close "<value>"` en config.kdl.

    - Reemplaza la primera linea no comentada que coincida.
    - Si no hay ninguna, agrega la directiva al final del archivo.
    - Crea backup si `backup=True`.
    Devuelve la ruta del backup creado o None.
    """
    if value not in ("detach", "quit"):
        raise ValueError(f"Invalid on_force_close value: {value!r}")

    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""

    backup_path: Path | None = None
    if backup and config_path.exists():
        backup_path = make_backup(config_path)

    new_text, replaced = _replace_first_uncommented(
        text, _ON_FORCE_CLOSE_LINE, f'on_force_close "{value}"'
    )
    if not replaced:
        sep = "" if text.endswith("\n") or text == "" else "\n"
        new_text = f'{text}{sep}on_force_close "{value}"\n'

    write_atomic(config_path, new_text)
    return backup_path


def _replace_first_uncommented(
    text: str, pattern: re.Pattern[str], replacement: str
) -> tuple[str, bool]:
    """Reemplaza el primer match no comentado del patron por `replacement`.
    Preserva el prefijo de indentacion. Devuelve (nuevo_texto, reemplazado)."""
    out: list[str] = []
    cursor = 0
    for match in pattern.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end_idx = text.find("\n", match.end())
        line_end = line_end_idx if line_end_idx != -1 else len(text)
        line = text[line_start:line_end]
        if _is_commented(line):
            continue
        out.append(text[cursor:line_start])
        prefix = match.group("prefix")
        out.append(f"{prefix}{replacement}")
        cursor = line_end
        out.append(text[cursor:])
        return "".join(out), True
    out.append(text[cursor:])
    return "".join(out), False


_SESSION_SERIALIZATION_LINE = re.compile(
    r"""^(?P<prefix>[ \t]*)session_serialization[ \t]+(?P<value>true|false)[ \t]*$""",
    re.MULTILINE,
)

_SERIALIZE_PANE_VIEWPORT_LINE = re.compile(
    r"""^(?P<prefix>[ \t]*)serialize_pane_viewport[ \t]+(?P<value>true|false)[ \t]*$""",
    re.MULTILINE,
)


def set_session_serialization(
    config_path: Path,
    value: bool,
    *,
    backup: bool = True,
) -> Path | None:
    """Escribe (o inserta) `session_serialization true/false` en config.kdl."""
    str_value = "true" if value else "false"
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    backup_path: Path | None = None
    if backup and config_path.exists():
        backup_path = make_backup(config_path)
    new_text, replaced = _replace_first_uncommented(
        text, _SESSION_SERIALIZATION_LINE, f"session_serialization {str_value}"
    )
    if not replaced:
        sep = "" if text.endswith("\n") or text == "" else "\n"
        new_text = f"{text}{sep}session_serialization {str_value}\n"
    write_atomic(config_path, new_text)
    return backup_path


def set_serialize_pane_viewport(
    config_path: Path,
    value: bool,
    *,
    backup: bool = True,
) -> Path | None:
    """Escribe (o inserta) `serialize_pane_viewport true/false` en config.kdl."""
    str_value = "true" if value else "false"
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    backup_path: Path | None = None
    if backup and config_path.exists():
        backup_path = make_backup(config_path)
    new_text, replaced = _replace_first_uncommented(
        text, _SERIALIZE_PANE_VIEWPORT_LINE, f"serialize_pane_viewport {str_value}"
    )
    if not replaced:
        sep = "" if text.endswith("\n") or text == "" else "\n"
        new_text = f"{text}{sep}serialize_pane_viewport {str_value}\n"
    write_atomic(config_path, new_text)
    return backup_path


def list_layouts(layouts_dir: Path) -> list[Layout]:
    """Devuelve los layouts en el directorio (no recursivo). Ordenados por nombre."""
    if not layouts_dir.exists():
        return []
    items: list[Layout] = []
    for path in sorted(layouts_dir.glob("*.kdl")):
        try:
            layout = layout_io.load_layout(path)
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
    "set_active_theme",
    "set_on_force_close",
    "set_serialize_pane_viewport",
    "set_session_serialization",
    "zellij_setup_check",
]
