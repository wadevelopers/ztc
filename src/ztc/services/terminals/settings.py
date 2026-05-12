"""Catalogo de settings canonicos cross-backend (Alacritty/Kitty) +
helpers de coercion y validacion.

Modelo paralelo a `ztc.services.colors.CanonicalSlot`: mientras los slots
son siempre `str` hex, las settings son heterogeneas (int/float/str/enum),
asi que cada entrada del catalogo declara su tipo.

Fuente unica de verdad: UI, backends e import consultan estos helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SettingKind(Enum):
    INT = "int"  # padding
    FLOAT = "float"  # opacity, font_size
    STR = "str"  # font_family
    ENUM = "enum"  # cursor_shape


@dataclass(frozen=True)
class CanonicalSetting:
    """Identificador estable + tipo + default + (para ENUM) valores validos.

    El `name` es el identificador canonico (e.g. `"window.padding.x"`); cada
    backend mapea desde aca al formato del archivo propio.
    """

    name: str
    kind: SettingKind
    default: object
    enum_values: tuple[str, ...] = field(default=())
    # Rango opcional para INT/FLOAT (min, max). None = sin limite.
    min_value: float | None = None
    max_value: float | None = None


# Catalogo de settings de iteracion 1.
SETTINGS: dict[str, CanonicalSetting] = {
    "window.columns": CanonicalSetting(
        "window.columns", SettingKind.INT, 80, min_value=1
    ),
    "window.lines": CanonicalSetting(
        "window.lines", SettingKind.INT, 25, min_value=1
    ),
    "window.padding.x": CanonicalSetting(
        "window.padding.x", SettingKind.INT, 0, min_value=0
    ),
    "window.padding.y": CanonicalSetting(
        "window.padding.y", SettingKind.INT, 0, min_value=0
    ),
    "window.opacity": CanonicalSetting(
        "window.opacity", SettingKind.FLOAT, 1.0, min_value=0.0, max_value=1.0
    ),
    "font.size": CanonicalSetting(
        "font.size", SettingKind.FLOAT, 12.0, min_value=1.0
    ),
    "font.family": CanonicalSetting("font.family", SettingKind.STR, "monospace"),
    "cursor.shape": CanonicalSetting(
        "cursor.shape",
        SettingKind.ENUM,
        "Block",
        enum_values=("Block", "Beam", "Underline"),
    ),
}


# ---------- coercion + validacion ----------


def coerce_setting_value(setting: CanonicalSetting, raw: object) -> object | None:
    """Convierte un valor crudo (lo que devuelve el parser TOML/conf) al
    tipo canonico de la setting. Devuelve None si no se puede coercionar
    limpio (ej. `font_size = "abc"`, padding `2.5` cuando el canon es int).

    Sin excepciones: los backends propagan None y la UI muestra "unset".
    """
    if raw is None:
        return None

    if setting.kind == SettingKind.INT:
        # Aceptamos int directo; rechazamos float no-entero o str no-numerico.
        if isinstance(raw, bool):
            return None
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float):
            return int(raw) if raw == int(raw) else None
        if isinstance(raw, str):
            try:
                f = float(raw)
            except ValueError:
                return None
            return int(f) if f == int(f) else None
        return None

    if setting.kind == SettingKind.FLOAT:
        if isinstance(raw, bool):
            return None
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str):
            try:
                return float(raw)
            except ValueError:
                return None
        return None

    if setting.kind == SettingKind.STR:
        if isinstance(raw, str):
            return raw
        return None

    if setting.kind == SettingKind.ENUM:
        if not isinstance(raw, str):
            return None
        # Match case-insensitive contra los enum_values; devolvemos la
        # forma canonica (capitalizada al estilo Alacritty).
        for valid in setting.enum_values:
            if raw.lower() == valid.lower():
                return valid
        return None

    return None


def validate_setting_value(setting: CanonicalSetting, value: object) -> bool:
    """True si value es valido segun setting.kind y restricciones.

    Lo usa la UI antes de habilitar "Guardar" y los backends antes de
    escribir (ver `write_setting` en TerminalBackend Protocol — levanta
    ValueError si esta funcion devuelve False).
    """
    if value is None:
        return False

    if setting.kind == SettingKind.INT:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and (setting.min_value is None or value >= setting.min_value)
            and (setting.max_value is None or value <= setting.max_value)
        )

    if setting.kind == SettingKind.FLOAT:
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and (setting.min_value is None or value >= setting.min_value)
            and (setting.max_value is None or value <= setting.max_value)
        )

    if setting.kind == SettingKind.STR:
        return isinstance(value, str) and len(value) > 0

    if setting.kind == SettingKind.ENUM:
        return isinstance(value, str) and value in setting.enum_values

    return False
