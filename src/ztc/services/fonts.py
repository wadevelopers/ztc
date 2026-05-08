"""Listado de fuentes monoespaciadas disponibles en el sistema via fontconfig.

Solo Linux/Wayland/X11 (fc-list). En sistemas sin fontconfig devuelve
lista vacia; el caller decide si usar fallback (input de texto libre) o
mostrar mensaje al usuario.
"""

from __future__ import annotations

import shutil
import subprocess


def list_monospace_fonts(timeout: float = 5.0) -> list[str]:
    """Devuelve los nombres de fuentes monoespaciadas del sistema, deduplicados
    y ordenados alfabeticamente.

    Output de `fc-list :spacing=mono family` viene como `family,alias1,alias2`
    por linea (cada alias es un nombre alternativo del mismo archivo). Tomamos
    el primer alias como nombre principal.

    Devuelve `[]` si fontconfig no esta instalado, falla o se cuelga.
    """
    fc = shutil.which("fc-list")
    if fc is None:
        return []
    try:
        proc = subprocess.run(
            [fc, ":spacing=mono", "family"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if proc.returncode != 0:
        return []
    families: set[str] = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Tomar el primer alias antes de la primera coma; desambigua casos
        # tipo "JetBrainsMono Nerd Font,JetBrainsMono NF,JetBrainsMono NF Bold".
        primary = line.split(",", 1)[0].strip()
        if primary:
            families.add(primary)
    return sorted(families)
