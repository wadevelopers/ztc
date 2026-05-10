"""Sincronizacion del tema de Zellij con los colores de la terminal.

Cuando se cambia el tema en el TUI, propagamos al menos `bg` y `fg` (y
los 8 ANSI normal si los tenemos) al backend de la terminal para que
combine con la sesion de Zellij. Mantiene backups y solo escribe los
slots que cambian.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ztc.services.colors import (
    CanonicalSlot,
    is_valid_hex,
    normalize_hex,
)
from ztc.services.terminals import TerminalBackend
from ztc.zellij import theme_assets as zta
from ztc.zellij.user_themes import list_user_themes

# Mapping 1:1 entre los 10 slots de la Paleta ANSI y los slots
# canonicos. fg/bg -> primary, los 8 ANSI -> normal.
LEGACY_TO_CANONICAL: dict[str, list[CanonicalSlot]] = {
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

# Mapping de slots ricos (formato nuevo de Zellij) a destinos canonicos.
_RICH_TO_CANONICAL: dict[tuple[str, str], list[CanonicalSlot]] = {
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
    updated: dict[CanonicalSlot, str]
    skipped_reason: str | None = None


def _resolve_zellij_slots(
    zellij_name: str, *, config_path: Path
) -> dict[str, str]:
    """Devuelve un dict slot_name -> hex (paleta legacy) para el tema dado.

    Prioriza user themes definidos en config.kdl. Si no es user, deriva
    desde los .kdl vendorizados. Si tampoco esta vendorizado, devuelve {}.
    """
    for ut in list_user_themes(config_path):
        if ut.name == zellij_name:
            return {c.name: c.value for c in ut.colors if is_valid_hex(c.value)}

    derived = zta.derive_legacy_slots_from_bundled(zellij_name)
    if derived is None:
        return {}
    return {k: v for k, v in derived.items() if is_valid_hex(v)}


def _resolve_zellij_rich_slots(
    zellij_name: str, *, config_path: Path
) -> dict[tuple[str, str], str]:
    """Devuelve {(component, slot): hex} con los slots del formato nuevo
    para el tema dado. Para user themes lee de raw_components, para
    built-in carga el .kdl vendorizado."""
    out: dict[tuple[str, str], str] = {}

    for ut in list_user_themes(config_path):
        if ut.name == zellij_name:
            for rc in ut.raw_components:
                comp = zta._parse_component(rc)
                for slot in _RICH_COMPONENT_SLOTS:
                    value = getattr(comp, slot, None)
                    if value and is_valid_hex(value):
                        out[(rc.name, slot)] = value
            return out

    bundled = zta.load_bundled_theme(zellij_name)
    if bundled is None:
        return out
    for comp_name, comp in bundled.components.items():
        for slot in _RICH_COMPONENT_SLOTS:
            value = getattr(comp, slot, None)
            if value and is_valid_hex(value):
                out[(comp_name, slot)] = value
    return out


def sync_terminal_with_zellij_theme(
    *,
    zellij_theme_name: str,
    backend: TerminalBackend,
    backend_path: Path,
    zellij_config_path: Path,
) -> SyncResult:
    """Aplica los colores del tema Zellij dado al archivo de la terminal.

    No toca otras secciones del archivo. Solo escribe slots cuyo valor
    cambia. Crea backup si hay cambios efectivos.
    """
    if not backend_path.exists():
        return SyncResult(
            backup=None,
            updated={},
            skipped_reason=f"{backend_path} does not exist",
        )

    slots = _resolve_zellij_slots(zellij_theme_name, config_path=zellij_config_path)
    rich_slots = _resolve_zellij_rich_slots(
        zellij_theme_name, config_path=zellij_config_path
    )
    if not slots and not rich_slots:
        return SyncResult(
            backup=None,
            updated={},
            skipped_reason=f"Theme '{zellij_theme_name}' has no extractable colors",
        )

    doc = backend.load(backend_path)
    updated: dict[CanonicalSlot, str] = {}

    def _apply(value: str, destinations: list[CanonicalSlot]) -> None:
        normalized = normalize_hex(value)
        for slot in destinations:
            current = backend.read_slot(doc, slot)
            if (
                current
                and is_valid_hex(current)
                and normalize_hex(current) == normalized
            ):
                continue
            backend.write_slot(doc, slot, normalized)
            updated[slot] = normalized

    for legacy_name, destinations in LEGACY_TO_CANONICAL.items():
        value = slots.get(legacy_name)
        if value is not None:
            _apply(value, destinations)

    for rich_key, destinations in _RICH_TO_CANONICAL.items():
        value = rich_slots.get(rich_key)
        if value is not None:
            _apply(value, destinations)

    if not updated:
        return SyncResult(backup=None, updated={}, skipped_reason="No changes")

    backup = backend.save(doc, backend_path)
    return SyncResult(backup=backup, updated=updated)
