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

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ztc.services.atomic import write_atomic
from ztc.services.backups import make_backup
from ztc.services.colors import CanonicalSlot
from ztc.services.terminals import default_import_theme_file
from ztc.services.terminals.settings import (
    SETTINGS,
    CanonicalSetting,
    coerce_setting_value,
    validate_setting_value,
)

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
_ZTC_PREF_RE = re.compile(r"^# ztc:(.*)$")


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


def read_remote_control(doc: KittyDoc) -> str | None:
    last = _last_entry_for_key(
        _linearize(doc.path, doc.lines, in_main=True),
        "allow_remote_control",
    )
    return last.value if last is not None else None


def is_remote_control_disabled(value: str | None) -> bool:
    return value is None or value == "no"


def write_remote_control_yes(doc: KittyDoc) -> None:
    doc.lines.append("allow_remote_control yes")


def read_listen_on(doc: KittyDoc) -> str | None:
    last = _last_entry_for_key(
        _linearize(doc.path, doc.lines, in_main=True),
        "listen_on",
    )
    return last.value if last is not None else None


def is_listen_on_set(value: str | None) -> bool:
    if value is None:
        return False
    stripped = value.strip()
    return bool(stripped) and stripped != "none"


def write_listen_on_default(doc: KittyDoc) -> None:
    doc.lines.append("listen_on unix:@ztc-{kitty_pid}")


def _parse_ztc_line(line: str) -> dict[str, object] | None:
    match = _ZTC_PREF_RE.match(line)
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _ztc_line_indices(lines: list[str]) -> list[int]:
    return [i for i, line in enumerate(lines) if _ZTC_PREF_RE.match(line)]


def _read_ztc_dict(doc: KittyDoc) -> dict[str, object]:
    out: dict[str, object] = {}
    for line in doc.lines:
        parsed = _parse_ztc_line(line)
        if parsed is not None:
            out.update(parsed)
    return out


def read_ztc_pref(doc: KittyDoc, key: str) -> object | None:
    return _read_ztc_dict(doc).get(key)


def write_ztc_pref(doc: KittyDoc, key: str, value: object) -> None:
    prefs = _read_ztc_dict(doc)
    prefs[key] = value
    ztc_indices = set(_ztc_line_indices(doc.lines))
    doc.lines = [line for i, line in enumerate(doc.lines) if i not in ztc_indices]
    doc.lines.append("# ztc:" + json.dumps(prefs, sort_keys=True))


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

    def reload_after_save(self, doc: KittyDoc, path: Path) -> bool:
        target = os.environ.get("KITTY_LISTEN_ON")
        current_instance = _current_kitty_instance_marker()
        pending_instance = read_ztc_pref(doc, "remote_control_pending_instance")
        if (
            not target
            and current_instance is not None
            and pending_instance == current_instance
        ):
            return False
        if not target and is_remote_control_disabled(read_remote_control(doc)):
            return False
        for binary in ("kitty", "kitten"):
            cmd = [binary, "@"]
            if target:
                cmd.extend(["--to", target])
            cmd.append("load-config")
            if not target:
                cmd.append("--no-response")
            try:
                result = subprocess.run(
                    cmd,
                    timeout=2,
                    capture_output=True,
                )
            except Exception:  # noqa: BLE001
                continue
            if result.returncode == 0:
                return True
        return False

    def manual_reload_hint(self) -> str:
        return "Press Ctrl+Shift+F5 in Kitty to reload."

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

    def import_theme_file(self, doc: KittyDoc, source_path: Path) -> int:
        return default_import_theme_file(self, doc, source_path)

    # ---------- settings (window, font, cursor) ----------

    def supported_settings(self) -> list[CanonicalSetting]:
        return [SETTINGS[name] for name in _SUPPORTED_SETTINGS_KITTY]

    def read_setting(
        self, doc: KittyDoc, setting: CanonicalSetting
    ) -> object | None:
        # Padding x/y comparten el key `window_padding_width` con
        # logica de 1-4 valores; manejado aparte.
        if setting.name in ("window.padding.x", "window.padding.y"):
            return _read_kitty_padding(self._effective_entries(doc), setting.name)

        key = _CANONICAL_TO_KITTY_SETTING.get(setting.name)
        if key is None:
            return None
        last = _last_entry_for_key(self._effective_entries(doc), key)
        if last is None:
            return None
        return coerce_setting_value(setting, last.value)

    def write_setting(
        self, doc: KittyDoc, setting: CanonicalSetting, value: object
    ) -> None:
        if not validate_setting_value(setting, value):
            raise ValueError(
                f"Invalid value for {setting.name!r} ({setting.kind.value}): {value!r}"
            )

        if setting.name in ("window.padding.x", "window.padding.y"):
            _write_kitty_padding(doc, setting.name, value)  # type: ignore[arg-type]
            return

        key = _CANONICAL_TO_KITTY_SETTING.get(setting.name)
        if key is None:
            raise KeyError(f"Setting {setting.name!r} not supported by Kitty")
        new_line = f"{key} {value}"
        last = _last_entry_for_key(self._effective_entries(doc), key)
        if last is not None and last.main_line_idx is not None:
            doc.lines[last.main_line_idx] = new_line
        else:
            doc.lines.append(new_line)

    def delete_setting(
        self, doc: KittyDoc, setting: CanonicalSetting
    ) -> bool:
        # Padding x/y borran ambos el key compartido (no podemos borrar
        # solo una direccion en Kitty: `window_padding_width` es un solo
        # key con 1-4 valores). Si solo se quiere resetear una direccion,
        # el caller deberia setear la otra explicitamente y dejar al
        # terminal usar su default. Aca, delete = borrar la linea entera.
        if setting.name in ("window.padding.x", "window.padding.y"):
            idx = _last_index_of_key_in_main(doc.lines, "window_padding_width")
            if idx is None:
                return False
            del doc.lines[idx]
            return True

        key = _CANONICAL_TO_KITTY_SETTING.get(setting.name)
        if key is None:
            return False
        idx = _last_index_of_key_in_main(doc.lines, key)
        if idx is None:
            return False
        del doc.lines[idx]
        return True


# ---------- mapeos y helpers de settings ----------

# Settings con mapeo directo 1:1 (key Kitty -> string del archivo).
# `window.padding.x` y `padding.y` no estan acá: comparten
# `window_padding_width` con logica especial (ver _read_kitty_padding /
# _write_kitty_padding).
_CANONICAL_TO_KITTY_SETTING: dict[str, str] = {
    "window.opacity": "background_opacity",
    "font.size": "font_size",
    "font.family": "font_family",
    "cursor.shape": "cursor_shape",
}

# Lista completa de settings soportadas (incluye padding x/y manejadas aparte).
_SUPPORTED_SETTINGS_KITTY: tuple[str, ...] = (
    "window.padding.x",
    "window.padding.y",
    "window.opacity",
    "font.size",
    "font.family",
    "cursor.shape",
)


def _parse_padding_values(raw: str) -> list[int] | None:
    """Parsea los valores numericos de `window_padding_width <values...>`.
    Devuelve None si algun valor no es int limpio (rechaza floats segun
    decision del plan: si Kitty tiene `2.5` el coerce devuelve None y la
    UI muestra unset).
    """
    parts = raw.strip().split()
    out: list[int] = []
    for p in parts:
        try:
            f = float(p)
        except ValueError:
            return None
        if f != int(f):
            return None
        out.append(int(f))
    return out if out else None


def _read_kitty_padding(entries: list[_Entry], setting_name: str) -> int | None:
    """Implementa la decision del plan para `window_padding_width`:
    - 1 valor: aplica a x e y.
    - 2 valores: vertical(y) horizontal(x).
    - 3 valores (top horizontal bottom): si top==bottom, asimetrico
      sobre y → no representable → None.
    - 4 valores (top right bottom left): simetrico si top==bottom y
      left==right → devolver y/x; asimetrico → None.
    - Floats no enteros → None (via _parse_padding_values).
    """
    last = _last_entry_for_key(entries, "window_padding_width")
    if last is None:
        return None
    values = _parse_padding_values(last.value)
    if values is None or not values:
        return None

    is_x = setting_name == "window.padding.x"

    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        # vertical horizontal → y x
        y, x = values
        return x if is_x else y
    if len(values) == 3:
        # top horizontal bottom: x = horizontal (limpio), y solo si top==bottom.
        top, h, bottom = values
        if is_x:
            return h
        return top if top == bottom else None
    if len(values) == 4:
        # top right bottom left: y simetrico si top==bottom; x simetrico si left==right.
        top, right, bottom, left = values
        if is_x:
            return right if right == left else None
        return top if top == bottom else None
    return None


def _write_kitty_padding(doc: KittyDoc, setting_name: str, value: int) -> None:
    """Escribe `window_padding_width Y X` (siempre 2 valores, vertical horizontal).
    Si solo se cambia una direccion, lee la otra del archivo (o usa 0 si no
    estaba) y compone la linea final.
    """
    entries = _linearize(doc.path, doc.lines, in_main=True)
    last = _last_entry_for_key(entries, "window_padding_width")
    current_x = current_y = 0
    if last is not None:
        values = _parse_padding_values(last.value)
        if values:
            if len(values) == 1:
                current_x = current_y = values[0]
            elif len(values) >= 2:
                current_y, current_x = values[0], values[1]

    if setting_name == "window.padding.x":
        new_x, new_y = value, current_y
    else:  # window.padding.y
        new_x, new_y = current_x, value

    new_line = f"window_padding_width {new_y} {new_x}"
    if last is not None and last.main_line_idx is not None:
        doc.lines[last.main_line_idx] = new_line
    else:
        doc.lines.append(new_line)


def _current_kitty_instance_marker() -> str | None:
    if pid := os.environ.get("KITTY_PID"):
        return f"pid:{pid}"
    if window_id := os.environ.get("KITTY_WINDOW_ID"):
        return f"window:{window_id}"
    return None
