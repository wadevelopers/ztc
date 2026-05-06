"""Utilidades genericas de color: validacion hex, contraste WCAG y
heuristicas de warning. Independientes del formato de archivo de la
terminal — operan sobre dicts de slots canonicos."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Slot canonico = (grupo, nombre). Compartido por todos los backends.
# Vocabulario: primary.{background,foreground} + normal.{8 ANSI} +
# bright.{8 ANSI} + selection.{text,background} + cursor.{text,cursor}.
CanonicalSlot = tuple[str, str]


_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


@dataclass(frozen=True)
class Warning:
    slot: CanonicalSlot | None
    message: str


def is_valid_hex(value: str) -> bool:
    return bool(_HEX.match(value.strip()))


def normalize_hex(value: str) -> str:
    """Devuelve el valor en minusculas con #. Asume que ya es hex valido."""
    return "#" + value.strip().lstrip("#").lower()


# ---------- contraste WCAG ----------


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    if not is_valid_hex(value):
        return None
    s = value.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) == 8:  # ignora alpha
        s = s[:6]
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _rel_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(a: str, b: str) -> float | None:
    """Ratio WCAG entre dos hex. Devuelve None si alguno es invalido. Rango 1..21."""
    rgb_a = _hex_to_rgb(a)
    rgb_b = _hex_to_rgb(b)
    if rgb_a is None or rgb_b is None:
        return None
    la = _rel_luminance(rgb_a)
    lb = _rel_luminance(rgb_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def compute_warnings(
    slots: dict[CanonicalSlot, str],
    *,
    zellij_bg: str | None = None,
) -> list[Warning]:
    """Detecta combinaciones problematicas. Heuristicas conservadoras:

    - background ~ normal.black: ratio < 1.5 -> aviso (puede confundir terminal apps).
    - background ~ zellij_bg: ratio < 1.3 -> aviso (UI de Zellij invisible).
    - selection.background ~ primary.background: ratio < 1.3 -> aviso.
    - cursor.cursor ~ primary.background: ratio < 2.0 -> aviso.
    - primary.foreground ~ primary.background: ratio < 4.5 -> aviso (WCAG AA texto).

    `slots` es un dict de slots canonicos (cualquier formato de
    terminal puede producirlo via su propio `read_slot`).
    """
    warnings: list[Warning] = []

    bg = slots.get(("primary", "background"))
    fg = slots.get(("primary", "foreground"))
    black = slots.get(("normal", "black"))
    sel_bg = slots.get(("selection", "background"))
    cur = slots.get(("cursor", "cursor"))

    if bg and fg:
        ratio = contrast_ratio(bg, fg)
        if ratio is not None and ratio < 4.5:
            warnings.append(
                Warning(
                    slot=("primary", "foreground"),
                    message=(
                        f"primary.foreground vs primary.background: contraste {ratio:.1f} "
                        "(WCAG recomienda >= 4.5 para texto)."
                    ),
                )
            )

    if bg and black:
        ratio = contrast_ratio(bg, black)
        if ratio is not None and ratio < 1.5:
            warnings.append(
                Warning(
                    slot=("normal", "black"),
                    message=(
                        f"primary.background y normal.black estan muy cerca (ratio {ratio:.2f}); "
                        "apps que usen 'black' sobre el fondo seran invisibles."
                    ),
                )
            )

    if bg and zellij_bg:
        ratio = contrast_ratio(bg, zellij_bg)
        if ratio is not None and ratio < 1.3:
            warnings.append(
                Warning(
                    slot=None,
                    message=(
                        f"primary.background ({bg}) vs zellij bg ({zellij_bg}): "
                        f"ratio {ratio:.2f}. Las barras de Zellij seran dificiles de ver."
                    ),
                )
            )

    if bg and sel_bg:
        ratio = contrast_ratio(bg, sel_bg)
        if ratio is not None and ratio < 1.3:
            warnings.append(
                Warning(
                    slot=("selection", "background"),
                    message=(
                        f"selection.background tiene poco contraste con el fondo "
                        f"(ratio {ratio:.2f}); la seleccion no se vera."
                    ),
                )
            )

    if bg and cur:
        ratio = contrast_ratio(bg, cur)
        if ratio is not None and ratio < 2.0:
            warnings.append(
                Warning(
                    slot=("cursor", "cursor"),
                    message=(
                        f"cursor.cursor tiene poco contraste con el fondo "
                        f"(ratio {ratio:.2f}); el cursor sera dificil de localizar."
                    ),
                )
            )

    return warnings
