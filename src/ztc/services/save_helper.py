from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ztc.services.terminals import BackendDoc, TerminalBackend


@dataclass(frozen=True)
class SaveResult:
    backup_path: Path | None
    reload_ok: bool
    manual_reload_hint: str | None = None


def save_with_reload(
    backend: TerminalBackend,
    doc: BackendDoc,
    path: Path,
) -> SaveResult:
    backup_path = backend.save(doc, path)
    reload_ok = backend.reload_after_save()
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
