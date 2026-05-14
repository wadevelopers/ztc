"""Helpers compartidos para Save-as, Load y G2 (conversion inicial a
manifest).

La validacion vive aca para no duplicar reglas entre `ColorEditorScreen`
y `TerminalSettingsScreen`. Cada screen orquesta su propio flow de UI
(modales, refresh) pero la decision "este path es valido" es la misma.
"""

from __future__ import annotations

from pathlib import Path

from ztc.services.terminals import TerminalBackend


def expected_extension(backend: TerminalBackend) -> str:
    """Extension esperada para perfiles del backend (`.toml`/`.conf`)."""
    return ".toml" if backend.kind == "alacritty" else ".conf"


def resolve_profile_path(name: str, base_dir: Path) -> Path:
    """Expande `~` y resuelve nombres relativos contra `base_dir`."""
    raw = Path(name).expanduser()
    return raw if raw.is_absolute() else (base_dir / raw)


def validate_profile_path(
    backend: TerminalBackend,
    path: Path,
) -> str | None:
    """Devuelve mensaje de error si el path no es valido, o None.

    Reglas:
    - Extension debe coincidir con la del backend (`.toml`/`.conf`).
    - Directory padre debe existir (no auto-crear; evita ensuciar
      `~/.config` con typos).

    NO chequea colision con archivo existente — eso es UI
    (`ConfirmActionModal`), decision del caller.

    NO chequea si `path == manifest_path` — el caller de Save-as maneja
    ese caso (es la operacion 'unmanage': volver a standalone) en lugar
    de rechazarlo.
    """
    expected = expected_extension(backend)
    if path.suffix.lower() != expected:
        return f"Filename must end with {expected}"
    if not path.parent.exists():
        return f"Directory does not exist: {path.parent}"
    return None
