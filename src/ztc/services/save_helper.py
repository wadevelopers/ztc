from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ztc.services.terminals import BackendDoc, TerminalBackend


@dataclass(frozen=True)
class SaveResult:
    backup_path: Path | None
    reload_ok: bool
    manual_reload_hint: str | None = None


def save_profile_with_reload(
    backend: TerminalBackend,
    profile_doc: BackendDoc,
    profile_path: Path,
    manifest_path: Path,
) -> SaveResult:
    """Guarda `profile_doc` al `profile_path` y dispara reload usando
    `manifest_path`. Necesario en Kitty porque las prefs runtime
    (`allow_remote_control`, `listen_on`, `remote_control_pending_instance`)
    viven en el manifest y no en el perfil; sin pasar el manifest el
    reload IPC bailearia con `return False`."""
    backup_path = backend.save(profile_doc, profile_path)
    reload_ok = backend.reload_after_profile_save(
        profile_doc, profile_path, manifest_path
    )
    hint = backend.manual_reload_hint() if not reload_ok else None
    return SaveResult(
        backup_path=backup_path,
        reload_ok=reload_ok,
        manual_reload_hint=hint,
    )


def compose_save_toast(file_name: str, result: SaveResult) -> str:
    msg = f"Saved: {file_name}"
    if result.backup_path is not None:
        msg += f"  (backup: {result.backup_path.name})"
    if not result.reload_ok and result.manual_reload_hint:
        msg += f"\n{result.manual_reload_hint}"
    return msg
