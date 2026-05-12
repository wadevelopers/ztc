"""Listado de fuentes monoespaciadas disponibles en el sistema via fontconfig.

Solo Linux/Wayland/X11 (fc-list). En sistemas sin fontconfig devuelve
lista vacia; el caller decide si usar fallback (input de texto libre) o
mostrar mensaje al usuario.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class FontFace:
    family: str
    style: str
    fallback: bool = False


@dataclass(frozen=True)
class FontFaceSet:
    normal: FontFace
    bold: FontFace
    italic: FontFace
    bold_italic: FontFace


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


def resolve_font_faces(family: str, timeout: float = 5.0) -> FontFaceSet:
    """Resuelve las 4 caras que deben escribirse para una familia.

    Si fontconfig no encuentra variantes reales de bold/italic, devuelve
    el estilo normal para esas caras. Eso evita que el terminal sustituya
    una fuente distinta cuando una fuente monoespaciada retro solo trae
    Regular.
    """
    normal_style, styles = _font_styles(family, timeout=timeout)
    normal = FontFace(family=family, style=normal_style)

    bold_style = _pick_style(styles, ("Bold",), reject=("Italic", "Oblique"))
    italic_style = _pick_style(
        styles,
        ("Italic", "Oblique"),
        reject=("Bold",),
    )
    bold_italic_style = _pick_style(
        styles,
        ("Bold Italic", "Bold Oblique"),
    )

    return FontFaceSet(
        normal=normal,
        bold=_face_or_fallback(family, bold_style, normal_style),
        italic=_face_or_fallback(family, italic_style, normal_style),
        bold_italic=_face_or_fallback(family, bold_italic_style, normal_style),
    )


def _font_styles(family: str, *, timeout: float) -> tuple[str, set[str]]:
    fc = shutil.which("fc-list")
    if fc is None:
        return "Regular", {"Regular"}
    try:
        proc = subprocess.run(
            [fc, f":family={family}:spacing=mono", "style"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "Regular", {"Regular"}
    if proc.returncode != 0:
        return "Regular", {"Regular"}

    styles: set[str] = set()
    for line in proc.stdout.splitlines():
        marker = "style="
        if marker not in line:
            continue
        _, raw_styles = line.split(marker, 1)
        for style in raw_styles.split(","):
            style = style.strip()
            if style:
                styles.add(style)

    if not styles:
        return "Regular", {"Regular"}
    return _pick_normal_style(styles), styles


def _pick_normal_style(styles: set[str]) -> str:
    for candidate in ("Regular", "Book", "Normal", "Roman", "Medium"):
        if candidate in styles:
            return candidate
    return sorted(styles)[0]


def _pick_style(
    styles: set[str],
    preferred: tuple[str, ...],
    *,
    reject: tuple[str, ...] = (),
) -> str | None:
    for candidate in preferred:
        if candidate in styles:
            return candidate
    for style in sorted(styles):
        style_lower = style.lower()
        if all(word.lower() in style_lower for word in preferred[0].split()):
            return style
        if any(word.lower() in style_lower for word in reject):
            continue
        if any(word.lower() in style_lower for word in preferred):
            return style
    return None


def _face_or_fallback(
    family: str,
    style: str | None,
    normal_style: str,
) -> FontFace:
    if style is None:
        return FontFace(family=family, style=normal_style, fallback=True)
    return FontFace(family=family, style=style)
