from __future__ import annotations

from pathlib import Path

import pytest

from ztc.services.save_helper import (
    SaveResult,
    compose_save_toast,
    save_profile_with_reload,
)


class _Backend:
    """Backend stub que captura los args pasados a `save` /
    `reload_after_profile_save` para verificar el contrato del helper."""

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
        self.reload_calls: list[tuple[object, Path, Path]] = []

    def save(self, doc: object, path: Path) -> Path | None:
        if self.save_error is not None:
            raise self.save_error
        self.saved = True
        return self.backup

    def reload_after_profile_save(
        self, doc: object, profile_path: Path, manifest_path: Path
    ) -> bool:
        self.reload_calls.append((doc, profile_path, manifest_path))
        return self.reload_ok

    def manual_reload_hint(self) -> str | None:
        return self.hint


def test_save_profile_with_reload_success(tmp_path: Path) -> None:
    backup = tmp_path / "terminal.conf.abc123.bak"
    backend = _Backend(backup=backup, reload_ok=True, hint="unused")
    profile_path = tmp_path / "c64.conf"
    manifest_path = tmp_path / "kitty.conf"
    result = save_profile_with_reload(backend, object(), profile_path, manifest_path)
    assert backend.saved is True
    # El reload recibe el profile y el manifest paths.
    assert len(backend.reload_calls) == 1
    _doc, prof, manif = backend.reload_calls[0]
    assert prof == profile_path
    assert manif == manifest_path
    assert result == SaveResult(
        backup_path=backup,
        reload_ok=True,
        manual_reload_hint=None,
    )


def test_save_profile_with_reload_failed_reload_includes_hint(tmp_path: Path) -> None:
    backup = tmp_path / "kitty.conf.xyz.bak"
    backend = _Backend(
        backup=backup,
        reload_ok=False,
        hint="Press Ctrl+Shift+F5 in Kitty to reload.",
    )
    result = save_profile_with_reload(
        backend, object(), tmp_path / "c64.conf", tmp_path / "kitty.conf"
    )
    assert result == SaveResult(
        backup_path=backup,
        reload_ok=False,
        manual_reload_hint="Press Ctrl+Shift+F5 in Kitty to reload.",
    )


def test_save_profile_with_reload_propagates_save_error(tmp_path: Path) -> None:
    backend = _Backend(save_error=RuntimeError("disk full"))
    with pytest.raises(RuntimeError, match="disk full"):
        save_profile_with_reload(
            backend, object(), tmp_path / "c64.conf", tmp_path / "kitty.conf"
        )


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
