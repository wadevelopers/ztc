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

# Mapping 1:1 entre los 10 slots de la Paleta ANSI y los slots
# correspondientes de Alacritty. fg/bg -> primary, los 8 ANSI -> normal.
_LEGACY_TO_ALACRITTY: dict[str, list[tuple[str, str]]] = {
    "fg": [("primary", "foreground")],
    "bg": [("primary", "background")],
    "black": [("normal", "black")],
    "red": [("normal", "red")],
    "green": [("normal", "green")],
    "yellow": [("normal", "yellow")],
    "blue": [("normal", "blue")],
    "magenta": [("normal", "magenta")],
    "cyan": [("normal", "cyan")],
    "white": [("normal", "white")],
}

# Mapping de slots ricos (formato nuevo de Zellij) a destinos Alacritty.
# (component, slot) -> [(alacritty_group, alacritty_name), ...]
_RICH_TO_ALACRITTY: dict[tuple[str, str], list[tuple[str, str]]] = {
    ("text_selected", "background"): [("selection", "background")],
    ("text_selected", "base"): [("selection", "text")],
}

_RICH_COMPONENT_SLOTS = (
    "base",
    "background",
    "emphasis_0",
    "emphasis_1",
    "emphasis_2",
    "emphasis_3",
)


@dataclass
class SyncResult:
    backup: Path | None
    updated: dict[tuple[str, str], str]
    skipped_reason: str | None = None


def _resolve_zellij_slots(
    zellij_name: str, *, config_path: Path
) -> dict[str, str]:
    """Devuelve un dict slot_name -> hex (paleta legacy) para el tema dado.

    Prioriza user themes definidos en config.kdl. Si no es user, deriva
    desde los .kdl vendorizados. Si tampoco esta vendorizado, devuelve {}.
    """
    for ut in zellij_themes.list_user_themes(config_path):
        if ut.name == zellij_name:
            return {c.name: c.value for c in ut.colors if alacritty.is_valid_hex(c.value)}

    derived = zta.derive_legacy_slots_from_bundled(zellij_name)
    if derived is None:
        return {}
    return {k: v for k, v in derived.items() if alacritty.is_valid_hex(v)}


def _resolve_zellij_rich_slots(
    zellij_name: str, *, config_path: Path
) -> dict[tuple[str, str], str]:
    """Devuelve {(component, slot): hex} con los slots del formato nuevo
    para el tema dado. Para user themes lee de raw_components, para
    built-in carga el .kdl vendorizado."""
    out: dict[tuple[str, str], str] = {}

    for ut in zellij_themes.list_user_themes(config_path):
        if ut.name == zellij_name:
            for rc in ut.raw_components:
                comp = zta._parse_component(rc)
                for slot in _RICH_COMPONENT_SLOTS:
                    value = getattr(comp, slot, None)
                    if value and alacritty.is_valid_hex(value):
                        out[(rc.name, slot)] = value
            return out

    bundled = zta.load_bundled_theme(zellij_name)
    if bundled is None:
        return out
    for comp_name, comp in bundled.components.items():
        for slot in _RICH_COMPONENT_SLOTS:
            value = getattr(comp, slot, None)
            if value and alacritty.is_valid_hex(value):
                out[(comp_name, slot)] = value
    return out


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
    rich_slots = _resolve_zellij_rich_slots(
        zellij_theme_name, config_path=zellij_config_path
    )
    if not slots and not rich_slots:
        return SyncResult(
            backup=None,
            updated={},
            skipped_reason=f"Tema '{zellij_theme_name}' sin colores extraibles",
        )

    doc = toml_io.load_toml(alacritty_path)
    updated: dict[tuple[str, str], str] = {}

    def _apply(value: str, destinations: list[tuple[str, str]]) -> None:
        normalized = alacritty.normalize_hex(value)
        for group, alacritty_name in destinations:
            current = alacritty.read_slot(doc, group, alacritty_name)
            if (
                current
                and alacritty.is_valid_hex(current)
                and alacritty.normalize_hex(current) == normalized
            ):
                continue
            alacritty.write_slot(doc, group, alacritty_name, normalized)
            updated[(group, alacritty_name)] = normalized

    for legacy_name, destinations in _LEGACY_TO_ALACRITTY.items():
        value = slots.get(legacy_name)
        if value is not None:
            _apply(value, destinations)

    for rich_key, destinations in _RICH_TO_ALACRITTY.items():
        value = rich_slots.get(rich_key)
        if value is not None:
            _apply(value, destinations)

    if not updated:
        return SyncResult(backup=None, updated={}, skipped_reason="Sin cambios")

    backup = toml_io.dump_toml(doc, alacritty_path)
    return SyncResult(backup=backup, updated=updated)
