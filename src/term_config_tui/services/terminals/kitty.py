"""Backend de Kitty: I/O sobre `kitty.conf`.

Sintaxis (verificado contra https://sw.kovidgoyal.net/kitty/conf):
- `key value` separado por whitespace (no `=`).
- Comentarios `#` al inicio de linea.
- Sin secciones; flat key-value.
- Hex aceptado: `#rrggbb` y `#rgb` (shorthand) — al leer expandimos
  a 6 digitos.
- Valores especiales (`none`, `background`, named colors, oklch(...),
  cielab(...)) se preservan tal cual; el editor los muestra con swatch
  vacio y solo se reemplazan si el usuario edita explicitamente.

Duplicados: kitty aplica last-occurrence-wins. `read_slot` devuelve la
ultima ocurrencia; `write_slot` actualiza la ultima. Si el slot no
existe, se appendea al final.

Includes (`include otro.conf`, `globinclude pat`): no se expanden al
leer. Esto significa que un slot definido en un archivo incluido no
se ve aca y, si lo escribimos en el archivo principal, kitty resolvera
segun su orden de carga (no garantizamos precedencia frente a includes).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from term_config_tui.services.atomic import write_atomic
from term_config_tui.services.backups import make_backup
from term_config_tui.services.colors import CanonicalSlot

# Mapping canonico -> nombre de key en kitty.conf.
_CANONICAL_TO_KITTY: dict[CanonicalSlot, str] = {
    ("primary", "background"): "background",
    ("primary", "foreground"): "foreground",
    ("normal", "black"): "color0",
    ("normal", "red"): "color1",
    ("normal", "green"): "color2",
    ("normal", "yellow"): "color3",
    ("normal", "blue"): "color4",
    ("normal", "magenta"): "color5",
    ("normal", "cyan"): "color6",
    ("normal", "white"): "color7",
    ("bright", "black"): "color8",
    ("bright", "red"): "color9",
    ("bright", "green"): "color10",
    ("bright", "yellow"): "color11",
    ("bright", "blue"): "color12",
    ("bright", "magenta"): "color13",
    ("bright", "cyan"): "color14",
    ("bright", "white"): "color15",
    ("selection", "text"): "selection_foreground",
    ("selection", "background"): "selection_background",
    ("cursor", "cursor"): "cursor",
    ("cursor", "text"): "cursor_text_color",
}

# Reverse para parsear: kitty key -> canonical slot.
_KITTY_TO_CANONICAL: dict[str, CanonicalSlot] = {
    v: k for k, v in _CANONICAL_TO_KITTY.items()
}

KNOWN_SLOTS: list[CanonicalSlot] = list(_CANONICAL_TO_KITTY.keys())

# Linea de config: "key value" con whitespace flexible. Tolera
# indentacion al inicio. Captura la clave (sin espacios) y el resto
# (que puede tener espacios para valores como `oklch(0.9 0.05 140)`).
_LINE_RE = re.compile(r"^\s*(\S+)\s+(.*?)\s*$")

# Hex con o sin # de 3 o 6 digitos. Lo usamos para normalizar al leer.
_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class KittyDoc:
    """Documento Kitty: lista de lineas (sin terminadores `\\n`).

    Mantiene las lineas tal cual vinieron del archivo; las modificaciones
    tocan la linea ganadora (ultima ocurrencia de la key) y appendean
    al final cuando la key no existe.
    """

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def to_text(self) -> str:
        # Re-emite como en el original: una linea por elemento + LF
        # final si habia (preservamos el comportamiento "termina en \\n").
        return "\n".join(self.lines) + "\n"


def _parse_line(line: str) -> tuple[str, str] | None:
    """Devuelve (key, value) o None si la linea es comentario/blanco/no parseable."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    m = _LINE_RE.match(line)
    if m is None:
        return None
    return m.group(1), m.group(2)


def _last_index_of_key(lines: list[str], key: str) -> int | None:
    """Indice de la ultima ocurrencia de `key` en `lines`, o None."""
    for i in range(len(lines) - 1, -1, -1):
        parsed = _parse_line(lines[i])
        if parsed is not None and parsed[0] == key:
            return i
    return None


def _normalize_value_if_hex(value: str) -> str:
    """Si el valor parsea como hex (`#fff`, `#abc123`, `abc123`),
    devuelve `#rrggbb` lowercase. Si no, lo deja tal cual (named color,
    `none`, `oklch(...)`, etc.)."""
    m = _HEX_RE.match(value.strip())
    if m is None:
        return value
    raw = m.group(1).lower()
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    return f"#{raw}"


class KittyBackend:
    """Backend para `kitty.conf`."""

    kind: str = "kitty"
    display_name: str = "Kitty"

    def default_config_path(self) -> Path:
        # Orden verificado contra docs oficiales:
        # $KITTY_CONFIG_DIRECTORY -> $XDG_CONFIG_HOME/kitty -> ~/.config/kitty
        env = os.environ
        kcd = env.get("KITTY_CONFIG_DIRECTORY")
        if kcd:
            return Path(kcd) / "kitty.conf"
        xdg = env.get("XDG_CONFIG_HOME")
        if xdg:
            return Path(xdg) / "kitty" / "kitty.conf"
        return Path.home() / ".config" / "kitty" / "kitty.conf"

    def supported_slots(self) -> list[CanonicalSlot]:
        return list(KNOWN_SLOTS)

    def load(self, path: Path) -> KittyDoc:
        if not path.exists():
            return KittyDoc(lines=[])
        text = path.read_text(encoding="utf-8")
        # split sin keepends, descartando el ultimo "" si el archivo
        # termina en \\n (lo restauramos en to_text).
        if text.endswith("\n"):
            text = text[:-1]
        return KittyDoc(lines=text.split("\n") if text else [])

    def save(self, doc: KittyDoc, path: Path) -> Path | None:
        backup = make_backup(path) if path.exists() else None
        write_atomic(path, doc.to_text())
        return backup

    def read_slot(self, doc: KittyDoc, slot: CanonicalSlot) -> str | None:
        key = _CANONICAL_TO_KITTY.get(slot)
        if key is None:
            return None
        idx = _last_index_of_key(doc.lines, key)
        if idx is None:
            return None
        parsed = _parse_line(doc.lines[idx])
        if parsed is None:
            return None
        return _normalize_value_if_hex(parsed[1])

    def write_slot(self, doc: KittyDoc, slot: CanonicalSlot, value: str) -> None:
        key = _CANONICAL_TO_KITTY.get(slot)
        if key is None:
            return
        idx = _last_index_of_key(doc.lines, key)
        new_line = f"{key} {value}"
        if idx is None:
            doc.lines.append(new_line)
        else:
            doc.lines[idx] = new_line

    def delete_slot(self, doc: KittyDoc, slot: CanonicalSlot) -> bool:
        key = _CANONICAL_TO_KITTY.get(slot)
        if key is None:
            return False
        idx = _last_index_of_key(doc.lines, key)
        if idx is None:
            return False
        del doc.lines[idx]
        return True
