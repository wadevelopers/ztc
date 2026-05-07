from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_atomic(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Escribe el archivo creando un .tmp en el mismo directorio y haciendo os.replace.

    Garantiza que un fallo a mitad de escritura no deja un archivo corrupto.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
