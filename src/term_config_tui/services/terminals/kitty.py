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

Includes (`include otro.conf`):
- Lectura: se expanden recursivamente con depth limit (5) para reflejar
  la realidad de kitty (la mayoria de configs incluyen un tema y los
  colores viven alli). Path relativo se resuelve contra el archivo
  padre. `globinclude` y `envinclude` NO se expanden — solo `include`.
  Si un include no existe, se ignora silenciosamente.
- Escritura: se toca SOLO el archivo principal (`default_config_path`).
  No modificamos archivos incluidos del usuario (temas, etc.).
  Si el slot ya esta en el archivo principal y nada despues lo
  sobrescribe, se actualiza la linea. Si solo viene de un include,
  se appendea al final del principal — kitty aplica last-wins en
  orden de carga, asi que nuestra linea (procesada al final) gana.

Duplicados dentro del mismo archivo: kitty aplica last-occurrence-wins.
`read_slot` resuelve linealizando main+includes en orden de procesamiento
y devolviendo la ultima coincidencia. `write_slot` actualiza la entrada
ganadora si es del main; si es de un include, appendea al main.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from term_config_tui.services.atomic import write_atomic
from term_config_tui.services.backups import make_backup
from zellij_themes.colors import CanonicalSlot

# Profundidad maxima para expandir `include`. Evita loops por
# circular includes y tambien acota el costo de parsing.
_MAX_INCLUDE_DEPTH = 5

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
    """Documento Kitty: lineas del archivo principal + path para
    resolver includes relativos.

    Solo se mutan las `lines` del principal. Los archivos incluidos
    se leen on-demand al hacer `read_slot` para reflejar el estado
    efectivo (last-wins en orden de procesamiento).
    """

    def __init__(self, path: Path, lines: list[str]) -> None:
        self.path = path
        self.lines = lines

    def to_text(self) -> str:
        # Re-emite como en el original: una linea por elemento + LF final.
        return "\n".join(self.lines) + "\n"


@dataclass(frozen=True)
class _Entry:
    """Una entrada key=value en orden de procesamiento, con info de origen."""

    key: str
    value: str
    main_line_idx: int | None
    """Indice en `lines` del archivo principal si la entrada vino del
    main; None si vino de un include."""


def _parse_line(line: str) -> tuple[str, str] | None:
    """Devuelve (key, value) o None si la linea es comentario/blanco/no parseable."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    m = _LINE_RE.match(line)
    if m is None:
        return None
    return m.group(1), m.group(2)


def _read_lines(path: Path) -> list[str]:
    """Lee un archivo y devuelve sus lineas sin terminadores. Vacio si no existe."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if text.endswith("\n"):
        text = text[:-1]
    return text.split("\n") if text else []


def _linearize(
    file_path: Path,
    lines: list[str],
    *,
    in_main: bool,
    depth: int = 0,
) -> list[_Entry]:
    """Procesa `lines` top-to-bottom; en cada `include otro.conf`
    recursivamente expande. Devuelve lista de entradas en orden de
    procesamiento de kitty (el ultimo de la lista es el "ganador" para
    cada key).

    `file_path` es el path del archivo cuyas `lines` se procesan; se
    usa para resolver paths relativos en `include`. `in_main=True` solo
    para el archivo principal (de ahi sale `main_line_idx`).
    """
    if depth > _MAX_INCLUDE_DEPTH:
        return []
    out: list[_Entry] = []
    base = file_path.parent
    for i, line in enumerate(lines):
        parsed = _parse_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if key == "include":
            target = Path(value)
            if not target.is_absolute():
                target = base / target
            try:
                inc_lines = _read_lines(target)
            except OSError:
                continue
            out.extend(
                _linearize(target, inc_lines, in_main=False, depth=depth + 1)
            )
            continue
        # globinclude / envinclude: no soportadas (caja de pandora);
        # las dejamos pasar como entradas no-color para no perderlas.
        out.append(
            _Entry(
                key=key,
                value=value,
                main_line_idx=i if in_main else None,
            )
        )
    return out


def _last_entry_for_key(entries: list[_Entry], key: str) -> _Entry | None:
    """Devuelve la ultima entrada con esa key (la que gana)."""
    for e in reversed(entries):
        if e.key == key:
            return e
    return None


def _last_index_of_key_in_main(lines: list[str], key: str) -> int | None:
    """Indice de la ultima ocurrencia de `key` en `lines` del main, o None."""
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
        return KittyDoc(path=path, lines=_read_lines(path))

    def save(self, doc: KittyDoc, path: Path) -> Path | None:
        backup = make_backup(path) if path.exists() else None
        write_atomic(path, doc.to_text())
        return backup

    def _effective_entries(self, doc: KittyDoc) -> list[_Entry]:
        return _linearize(doc.path, doc.lines, in_main=True)

    def read_slot(self, doc: KittyDoc, slot: CanonicalSlot) -> str | None:
        key = _CANONICAL_TO_KITTY.get(slot)
        if key is None:
            return None
        entries = self._effective_entries(doc)
        last = _last_entry_for_key(entries, key)
        if last is None:
            return None
        return _normalize_value_if_hex(last.value)

    def write_slot(self, doc: KittyDoc, slot: CanonicalSlot, value: str) -> None:
        """Escribe SOLO al archivo principal.

        - Si la entrada ganadora es del main: actualiza esa linea.
        - Si la entrada ganadora viene de un include (o no existe):
          appendea al final del main para que kitty la procese al final
          y gane via last-wins.
        """
        key = _CANONICAL_TO_KITTY.get(slot)
        if key is None:
            return
        entries = self._effective_entries(doc)
        last = _last_entry_for_key(entries, key)
        new_line = f"{key} {value}"
        if last is not None and last.main_line_idx is not None:
            doc.lines[last.main_line_idx] = new_line
        else:
            doc.lines.append(new_line)

    def delete_slot(self, doc: KittyDoc, slot: CanonicalSlot) -> bool:
        """Borra la ultima ocurrencia del main. No toca includes.

        Despues del delete, si el slot estaba siendo provisto por un
        include, ese valor pasa a ser el efectivo (semantica correcta
        de kitty). Devuelve True si habia algo que borrar en el main.
        """
        key = _CANONICAL_TO_KITTY.get(slot)
        if key is None:
            return False
        idx = _last_index_of_key_in_main(doc.lines, key)
        if idx is None:
            return False
        del doc.lines[idx]
        return True
