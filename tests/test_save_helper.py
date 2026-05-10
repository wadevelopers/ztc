from __future__ import annotations

from pathlib import Path

import pytest

from ztc.services.save_helper import SaveResult, compose_save_toast, save_with_reload


class _Backend:
    def __init__(
        self,
        *,
        backup: Path | None = None,
        reload_ok: bool = True,
        hint: str | None = None,
        save_error: Exception | None = None,
    ) -> None:
        self.backup = backup
        self.reload_ok = reload_ok
        self.hint = hint
        self.save_error = save_error
        self.saved = False

    def save(self, doc: object, path: Path) -> Path | None:
        if self.save_error is not None:
            raise self.save_error
        self.saved = True
        return self.backup

    def reload_after_save(self) -> bool:
        return self.reload_ok

    def manual_reload_hint(self) -> str | None:
        return self.hint


def test_save_with_reload_success_with_backup(tmp_path: Path) -> None:
    backup = tmp_path / "terminal.conf.bak"
    backend = _Backend(backup=backup, reload_ok=True, hint="unused")
    result = save_with_reload(backend, object(), tmp_path / "terminal.conf")
    assert backend.saved is True
    assert result == SaveResult(
        backup_path=backup,
        reload_ok=True,
        manual_reload_hint=None,
    )


def test_save_with_reload_failed_reload_includes_hint(tmp_path: Path) -> None:
    backup = tmp_path / "kitty.conf.bak"
    backend = _Backend(
        backup=backup,
        reload_ok=False,
        hint="Press Ctrl+Shift+F5 in Kitty to reload.",
    )
    result = save_with_reload(backend, object(), tmp_path / "kitty.conf")
    assert result == SaveResult(
        backup_path=backup,
        reload_ok=False,
        manual_reload_hint="Press Ctrl+Shift+F5 in Kitty to reload.",
    )


def test_save_with_reload_propagates_save_error(tmp_path: Path) -> None:
    backend = _Backend(save_error=RuntimeError("disk full"))
    with pytest.raises(RuntimeError, match="disk full"):
        save_with_reload(backend, object(), tmp_path / "terminal.conf")


def test_compose_save_toast_variants(tmp_path: Path) -> None:
    assert (
        compose_save_toast(
            "alacritty.toml",
            SaveResult(tmp_path / "alacritty.toml.bak", True),
        )
        == "Saved: alacritty.toml  (backup: alacritty.toml.bak)"
    )
    assert (
        compose_save_toast(
            "kitty.conf",
            SaveResult(
                tmp_path / "kitty.conf.bak",
                False,
                "Press Ctrl+Shift+F5 in Kitty to reload.",
            ),
        )
        == "Saved: kitty.conf  (backup: kitty.conf.bak)\n"
        "Press Ctrl+Shift+F5 in Kitty to reload."
    )
