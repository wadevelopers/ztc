from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def backup_path_for(path: Path, *, now: datetime | None = None) -> Path:
    """Devuelve la ruta del backup con timestamp YYYYMMDD-HHMMSS junto al original."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return path.with_name(f"{path.name}.bak.{stamp}")


def make_backup(path: Path, *, now: datetime | None = None) -> Path | None:
    """Copia el archivo a su ruta de backup. Devuelve la ruta creada o None si no existe."""
    if not path.exists():
        return None
    dst = backup_path_for(path, now=now)
    shutil.copy2(path, dst)
    return dst
