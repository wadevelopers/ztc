"""Sincronizacion del tema de Zellij con los colores de Alacritty.

Cuando se cambia el tema en el TUI, propagamos al menos `bg` y `fg` (y los
8 ANSI normal si los tenemos) a `alacritty.toml` para que la terminal
combine con la sesion de Zellij. Mantiene backups y solo escribe los
slots que cambian.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from term_config_tui.services import alacritty, toml_io, zellij_themes
from term_config_tui.services import zellij_theme_assets as zta

# Mapeo de slot legacy de Zellij a (group, name) de Alacritty.
_LEGACY_TO_ALACRITTY: dict[str, tuple[str, str]] = {
    "fg": ("primary", "foreground"),
    "bg": ("primary", "background"),
    "black": ("normal", "black"),
    "red": ("normal", "red"),
    "green": ("normal", "green"),
    "yellow": ("normal", "yellow"),
    "blue": ("normal", "blue"),
    "magenta": ("normal", "magenta"),
    "cyan": ("normal", "cyan"),
    "white": ("normal", "white"),
}


@dataclass
class SyncResult:
    backup: Path | None
    updated: dict[tuple[str, str], str]
    skipped_reason: str | None = None


def _resolve_zellij_slots(
    zellij_name: str, *, config_path: Path
) -> dict[str, str]:
    """Devuelve un dict slot_name -> hex para el tema dado.

    Prioriza user themes definidos en config.kdl. Si no es user, intenta
    derivar slots desde los .kdl vendorizados. Si tampoco esta vendorizado,
    devuelve un dict vacio.
    """
    for ut in zellij_themes.list_user_themes(config_path):
        if ut.name == zellij_name:
            return {c.name: c.value for c in ut.colors if alacritty.is_valid_hex(c.value)}

    derived = zta.derive_legacy_slots_from_bundled(zellij_name)
    if derived is None:
        return {}
    return {k: v for k, v in derived.items() if alacritty.is_valid_hex(v)}


def sync_alacritty_with_zellij_theme(
    *,
    zellij_theme_name: str,
    alacritty_path: Path,
    zellij_config_path: Path,
) -> SyncResult:
    """Aplica los colores del tema Zellij dado a alacritty.toml.

    No toca otras secciones del TOML. Solo escribe slots cuyo valor cambia.
    Crea backup si hay cambios efectivos.
    """
    if not alacritty_path.exists():
        return SyncResult(
            backup=None,
            updated={},
            skipped_reason=f"No existe {alacritty_path}",
        )

    slots = _resolve_zellij_slots(zellij_theme_name, config_path=zellij_config_path)
    if not slots:
        return SyncResult(
            backup=None,
            updated={},
            skipped_reason=f"Tema '{zellij_theme_name}' sin colores extraibles",
        )

    doc = toml_io.load_toml(alacritty_path)
    updated: dict[tuple[str, str], str] = {}
    for legacy_name, (group, alacritty_name) in _LEGACY_TO_ALACRITTY.items():
        value = slots.get(legacy_name)
        if value is None:
            continue
        normalized = alacritty.normalize_hex(value)
        current = alacritty.read_slot(doc, group, alacritty_name)
        if (
            current
            and alacritty.is_valid_hex(current)
            and alacritty.normalize_hex(current) == normalized
        ):
            continue
        alacritty.write_slot(doc, group, alacritty_name, normalized)
        updated[(group, alacritty_name)] = normalized

    if not updated:
        return SyncResult(backup=None, updated={}, skipped_reason="Sin cambios")

    backup = toml_io.dump_toml(doc, alacritty_path)
    return SyncResult(backup=backup, updated=updated)
