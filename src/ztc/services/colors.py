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

# Formatos de color que Zellij acepta para `default_bg` / `default_fg`
# en layouts. Verificado empiricamente: los cuatro renderizan con el
# color declarado. El alpha en `#rrggbbaa` se acepta sintacticamente
# pero Zellij lo ignora al renderizar (terminales no hacen blending).
_ZELLIJ_PANE_COLOR = re.compile(
    r"^(?:"
    r"#[0-9a-fA-F]{3}"           # #rgb
    r"|#[0-9a-fA-F]{6}"          # #rrggbb
    r"|#[0-9a-fA-F]{8}"          # #rrggbbaa (alpha ignorado visualmente)
    r"|rgb:[0-9a-fA-F]{2}/[0-9a-fA-F]{2}/[0-9a-fA-F]{2}"  # rgb:rr/gg/bb
    r")$"
)


@dataclass(frozen=True)
class Warning:
    slot: CanonicalSlot | None
    message: str


def is_valid_hex(value: str) -> bool:
    return bool(_HEX.match(value.strip()))


def is_valid_zellij_pane_color(value: str) -> bool:
    """Valida formatos aceptados por Zellij para `default_bg` /
    `default_fg`. Acepta `#rgb`, `#rrggbb`, `#rrggbbaa` (alpha
    ignorado) y `rgb:rr/gg/bb`. Mas permisivo que `is_valid_hex`,
    que rechaza la sintaxis `rgb:...`."""
    return bool(_ZELLIJ_PANE_COLOR.match(value.strip()))


def zellij_color_to_rich_hex(value: str) -> str | None:
    """Convierte un color en formato Zellij a un `#rrggbb` que Rich
    entiende para usar como bg/fg en markup. Devuelve None si el
    formato no es valido.

    Necesario porque Rich entiende `#rgb`, `#rrggbb`, `#rrggbbaa`
    pero NO `rgb:rr/gg/bb` (sintaxis X11). El alpha en `#rrggbbaa`
    se descarta — Rich no compone bg con alpha."""
    s = value.strip()
    if not is_valid_zellij_pane_color(s):
        return None
    if s.startswith("#"):
        body = s[1:]
        if len(body) == 3:
            # Expandir #rgb -> #rrggbb
            return "#" + "".join(c * 2 for c in body)
        if len(body) == 8:
            # Truncar alpha
            return "#" + body[:6]
        return s  # ya es #rrggbb
    if s.startswith("rgb:"):
        # rgb:6c/72/a4 -> #6c72a4
        parts = s[4:].split("/")
        if len(parts) == 3:
            return "#" + "".join(parts)
    return None


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

    - selection.background ~ primary.background: ratio < 1.3 -> aviso.
    - cursor.cursor ~ primary.background: ratio < 2.0 -> aviso.
    - primary.foreground ~ primary.background: ratio < 4.5 -> aviso (WCAG AA texto).

    `slots` es un dict de slots canonicos (cualquier formato de
    terminal puede producirlo via su propio `read_slot`).

    `zellij_bg` se acepta por compatibilidad de la firma; ya no se
    usa para warnings (theme_sync hace bg == zellij_bg por diseño,
    asi que el aviso era falso positivo).
    """
    warnings: list[Warning] = []

    bg = slots.get(("primary", "background"))
    fg = slots.get(("primary", "foreground"))
    sel_bg = slots.get(("selection", "background"))
    cur = slots.get(("cursor", "cursor"))

    if bg and fg:
        ratio = contrast_ratio(bg, fg)
        if ratio is not None and ratio < 4.5:
            warnings.append(
                Warning(
                    slot=("primary", "foreground"),
                    message=(
                        f"primary.foreground vs primary.background: contrast {ratio:.1f} "
                        "(WCAG recommends >= 4.5 for text)."
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
                        f"selection.background has low contrast with the background "
                        f"(ratio {ratio:.2f}); the selection will not be visible."
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
                        f"cursor.cursor has low contrast with the background "
                        f"(ratio {ratio:.2f}); the cursor will be hard to locate."
                    ),
                )
            )

    return warnings
