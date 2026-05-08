"""Listado de layouts disponibles y resolución del default."""

from __future__ import annotations

import os
import re
from pathlib import Path

_DEFAULT_LAYOUT_LINE = re.compile(r'^\s*default_layout\s+"([^"]+)"', re.MULTILINE)


def default_layouts_dir() -> Path:
    """Directorio estándar de layouts de Zellij."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "zellij" / "layouts"


def list_layout_files(layouts_dir: Path | None = None) -> list[str]:
    """Devuelve los nombres (sin .kdl) de los layouts en el directorio."""
    layouts_dir = layouts_dir or default_layouts_dir()
    if not layouts_dir.exists():
        return []
    return sorted(p.stem for p in layouts_dir.glob("*.kdl"))


def zellij_default_layout(config_path: Path | None = None) -> str | None:
    """Lee `default_layout "..."` de `~/.config/zellij/config.kdl`. None si
    no aparece o el archivo no existe."""
    if config_path is None:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        config_path = Path(base) / "zellij" / "config.kdl"
    if not config_path.exists():
        return None
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _DEFAULT_LAYOUT_LINE.search(text)
    return m.group(1) if m else None
