from __future__ import annotations

from pathlib import Path

import tomlkit
from tomlkit.toml_document import TOMLDocument

from ztc.services.atomic import write_atomic
from ztc.services.backups import make_backup


def load_toml(path: Path) -> TOMLDocument:
    """Carga un TOML preservando formato, comentarios y orden."""
    if not path.exists():
        return tomlkit.document()
    return tomlkit.parse(path.read_text(encoding="utf-8"))


def dump_toml(doc: TOMLDocument, path: Path, *, backup: bool = True) -> Path | None:
    """Escribe atomicamente. Crea backup si el archivo existia."""
    backup_path: Path | None = None
    if backup and path.exists():
        backup_path = make_backup(path)
    write_atomic(path, tomlkit.dumps(doc))
    return backup_path


__all__ = ["load_toml", "dump_toml", "tomlkit", "TOMLDocument"]
