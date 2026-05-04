from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

# Cuantos backups mantenemos por archivo. Al crear uno nuevo, los mas
# viejos por encima de este limite se borran.
KEEP_BACKUPS = 5


def backup_path_for(path: Path, *, now: datetime | None = None) -> Path:
    """Devuelve la ruta del backup con timestamp YYYYMMDD-HHMMSS junto al original."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return path.with_name(f"{path.name}.bak.{stamp}")


def list_backups(path: Path) -> list[Path]:
    """Lista los backups de `path`, ordenados de mas nuevo a mas viejo.
    El timestamp del nombre (YYYYMMDD-HHMMSS) ordena cronologicamente."""
    parent = path.parent
    if not parent.exists():
        return []
    return sorted(parent.glob(f"{path.name}.bak.*"), reverse=True)


def prune_old_backups(path: Path, *, keep: int = KEEP_BACKUPS) -> list[Path]:
    """Borra los backups por encima del limite, dejando los `keep` mas
    recientes. Devuelve las rutas eliminadas."""
    deleted: list[Path] = []
    for old in list_backups(path)[keep:]:
        try:
            old.unlink()
            deleted.append(old)
        except OSError:
            pass
    return deleted


def make_backup(path: Path, *, now: datetime | None = None) -> Path | None:
    """Copia el archivo a su ruta de backup y rota los antiguos.
    Devuelve la ruta creada o None si el original no existe."""
    if not path.exists():
        return None
    dst = backup_path_for(path, now=now)
    shutil.copy2(path, dst)
    prune_old_backups(path)
    return dst
