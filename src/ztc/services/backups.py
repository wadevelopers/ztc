from __future__ import annotations

import hashlib
import os
import shutil
import time
from pathlib import Path

# Cuantos backups mantenemos por archivo. Al crear uno nuevo, los mas
# viejos por encima de este limite se borran.
KEEP_BACKUPS = 5

# Longitud del hash corto que identifica el backup. SHA256 truncado a 8
# hex chars = 32 bits ~ 4×10^9 combinaciones; colision astronomica con
# KEEP_BACKUPS=5 por archivo.
_HASH_LEN = 8


def _content_hash(path: Path) -> str:
    """Hash corto SHA256 truncado del contenido del archivo. Identifica
    el snapshot de forma unica sin metadata temporal en el nombre — la
    fecha/hora viene del `mtime` del archivo (propiedades del filesystem)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:_HASH_LEN]


def backup_path_for(path: Path) -> Path:
    """Devuelve la ruta del backup junto al original.

    Formato: `<name>.<hash8>.bak`. El `.bak` queda como sufijo identificable
    (filtros tipo `*.bak` lo agarran limpio). La fecha/hora se obtiene del
    `mtime` del archivo, no del nombre.

    Requiere que `path` exista (necesita leer el contenido para hashear)."""
    return path.with_name(f"{path.name}.{_content_hash(path)}.bak")


def list_backups(path: Path) -> list[Path]:
    """Lista los backups de `path`, ordenados de mas nuevo a mas viejo
    por `mtime` (la fecha/hora ya no esta en el nombre)."""
    parent = path.parent
    if not parent.exists():
        return []
    candidates = parent.glob(f"{path.name}.*.bak")
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)


def prune_old_backups(path: Path, *, keep: int = KEEP_BACKUPS) -> list[Path]:
    """Borra los backups por encima del limite, dejando los `keep` mas
    recientes por `mtime`. Devuelve las rutas eliminadas."""
    deleted: list[Path] = []
    for old in list_backups(path)[keep:]:
        try:
            old.unlink()
            deleted.append(old)
        except OSError:
            pass
    return deleted


def make_backup(path: Path) -> Path | None:
    """Copia el archivo a su ruta de backup y rota los antiguos.
    Devuelve la ruta creada (o existente si era idempotente), o None si
    el original no existe.

    Idempotencia: si el backup con el hash del contenido actual ya existe,
    no crea duplicados — retorna el path existente. Esto significa que
    guardar el mismo contenido N veces produce un solo backup."""
    if not path.exists():
        return None
    dst = backup_path_for(path)
    if dst.exists():
        return dst
    shutil.copy2(path, dst)
    # `shutil.copy2` preserva el mtime del source. Si varios saves
    # ocurren en sucesion rapida, todos los backups quedarian con mtime
    # casi identico y la rotation por mtime se vuelve ambigua (el backup
    # recien creado podria caer en el rotation y borrarse). Forzar
    # mtime=now_ns garantiza orden estricto.
    now_ns = time.time_ns()
    os.utime(dst, ns=(now_ns, now_ns))
    prune_old_backups(path)
    return dst
