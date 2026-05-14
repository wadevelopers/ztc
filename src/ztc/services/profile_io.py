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
    *,
    manifest_path: Path | None = None,
    forbidden_path: Path | None = None,
) -> str | None:
    """Devuelve mensaje de error si el path no es valido, o None.

    Reglas:
    - Extension debe coincidir con la del backend (`.toml`/`.conf`).
    - Directory padre debe existir (no auto-crear; evita ensuciar
      `~/.config` con typos).
    - Si `manifest_path` se pasa y coincide con `path`, error claro: el
      manifest no puede ser usado como nombre de perfil porque crearia
      una auto-referencia (`include kitty.conf` dentro de `kitty.conf`)
      → recursion infinita al reload, y si el caller es Save-as
      sobrescribiria las managed directives. Save-in-place sobre el
      activo NO pasa por esta validacion (el caller hace el branch
      antes).
    - Si `forbidden_path` se pasa y coincide con `path`, error claro
      (caso edge del flow Load+G2: el nombre del primer perfil no puede
      ser igual al perfil que se esta cargando).

    NO chequea colision con archivo existente — eso es UI
    (`ConfirmActionModal`), decision del caller.
    """
    expected = expected_extension(backend)
    if path.suffix.lower() != expected:
        return f"Filename must end with {expected}"
    if not path.parent.exists():
        return f"Directory does not exist: {path.parent}"
    if manifest_path is not None and path == manifest_path:
        return (
            f"Cannot use the manifest file ({manifest_path.name}) as a "
            "profile name; choose another"
        )
    if forbidden_path is not None and path == forbidden_path:
        return "Name collides with the profile you're loading; choose another"
    return None
