"""Tests del state del app relacionado a perfiles intercambiables.

Cubre:
- Inicializacion de `backend_manifest_path` vs `backend_path` segun si
  el archivo es manifest o standalone.
- `set_active_profile` con orden transaccional:
  - write_active_profile falla → state NO cambia + excepcion propaga.
  - reload_after_profile_switch falla → state SI cambia + warning toast.
  - happy path → state cambia + sin warning.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ztc.app import TermConfigApp
from ztc.models.config import Paths
from ztc.services.runtime_detect import TerminalDetection
from ztc.services.terminals.alacritty import AlacrittyBackend


def _paths(tmp_path: Path) -> Paths:
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    return Paths(zellij_config=cfg, zellij_layouts_dir=tmp_path / "layouts")


def _detection() -> TerminalDetection:
    return TerminalDetection(
        kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
    )


# ---------- init: state de manifest vs perfil ----------


def test_init_standalone_config_falls_back_to_manifest_path(tmp_path: Path) -> None:
    """Archivo sin marker: `backend_path` cae al `backend_manifest_path`."""
    path = tmp_path / "alacritty.toml"
    path.write_text('[window]\nopacity = 0.9\n', encoding="utf-8")
    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=path,
        detection=_detection(),
        zellij_installed=True,
    )
    assert app.backend_manifest_path == path
    assert app.backend_path == path


def test_init_managed_manifest_resolves_active_profile(tmp_path: Path) -> None:
    """Archivo con marker + import: `backend_path` apunta al perfil activo."""
    manifest = tmp_path / "alacritty.toml"
    manifest.write_text(
        "[ztc]\nmanaged_manifest = true\n\n"
        '[general]\nimport = ["c64.toml"]\n',
        encoding="utf-8",
    )
    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=manifest,
        detection=_detection(),
        zellij_installed=True,
    )
    assert app.backend_manifest_path == manifest
    assert app.backend_path == tmp_path / "c64.toml"


def test_init_missing_file_keeps_path_as_both(tmp_path: Path) -> None:
    """Si el archivo no existe (primer run), manifest_path y backend_path
    apuntan al mismo path. `set_active_profile` no se llama todavia."""
    path = tmp_path / "alacritty.toml"  # no existe
    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=path,
        detection=_detection(),
        zellij_installed=True,
    )
    assert app.backend_manifest_path == path
    assert app.backend_path == path


# ---------- set_active_profile: orden transaccional ----------


async def test_set_active_profile_happy_path_updates_state(tmp_path: Path) -> None:
    """Caso feliz: write OK + reload OK → backend_path cambia, sin notify."""
    manifest = tmp_path / "alacritty.toml"
    manifest.write_text(
        "[ztc]\nmanaged_manifest = true\n\n"
        '[general]\nimport = ["c64.toml"]\n',
        encoding="utf-8",
    )
    (tmp_path / "c64.toml").write_text("# c64\n", encoding="utf-8")
    (tmp_path / "vga.toml").write_text("# vga\n", encoding="utf-8")

    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=manifest,
        detection=_detection(),
        zellij_installed=True,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.backend_path == tmp_path / "c64.toml"
        notifications: list[tuple[str, str]] = []
        app.notify = lambda msg, **kw: notifications.append(  # type: ignore[method-assign]
            (msg, kw.get("severity", "information"))
        )

        app.set_active_profile(tmp_path / "vga.toml")
        # State cambio al nuevo perfil.
        assert app.backend_path == tmp_path / "vga.toml"
        # Manifest reescrito apuntando al nuevo perfil.
        assert app.backend.read_active_profile(manifest) == tmp_path / "vga.toml"
        # No notify (Alacritty siempre retorna True desde reload).
        assert notifications == []


async def test_set_active_profile_write_failure_keeps_state(tmp_path: Path) -> None:
    """write_active_profile lanza excepcion → propaga + backend_path NO
    cambia + manifest NO se modifica."""
    manifest = tmp_path / "alacritty.toml"
    manifest.write_text(
        "[ztc]\nmanaged_manifest = true\n\n"
        '[general]\nimport = ["c64.toml"]\n',
        encoding="utf-8",
    )
    (tmp_path / "c64.toml").write_text("# c64\n", encoding="utf-8")

    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=manifest,
        detection=_detection(),
        zellij_installed=True,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        original_path = app.backend_path

        def fake_write_active_profile(manifest_path: Path, profile_path: Path) -> None:
            raise OSError("disk full")

        app.backend.write_active_profile = fake_write_active_profile  # type: ignore[method-assign]

        with pytest.raises(OSError, match="disk full"):
            app.set_active_profile(tmp_path / "vga.toml")
        # State NO cambio.
        assert app.backend_path == original_path


async def test_set_active_profile_reload_failure_keeps_new_state(
    tmp_path: Path,
) -> None:
    """write OK + reload retorna False → backend_path SI cambia + warning
    toast con manual_reload_hint."""
    manifest = tmp_path / "alacritty.toml"
    manifest.write_text(
        "[ztc]\nmanaged_manifest = true\n\n"
        '[general]\nimport = ["c64.toml"]\n',
        encoding="utf-8",
    )
    (tmp_path / "c64.toml").write_text("# c64\n", encoding="utf-8")
    (tmp_path / "vga.toml").write_text("# vga\n", encoding="utf-8")

    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=manifest,
        detection=_detection(),
        zellij_installed=True,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        notifications: list[tuple[str, str]] = []
        app.notify = lambda msg, **kw: notifications.append(  # type: ignore[method-assign]
            (msg, kw.get("severity", "information"))
        )

        def fake_reload(manifest_path: Path, new_profile_path: Path) -> bool:
            return False

        def fake_hint() -> str:
            return "Custom hint"

        app.backend.reload_after_profile_switch = fake_reload  # type: ignore[method-assign]
        app.backend.manual_reload_hint = fake_hint  # type: ignore[method-assign]

        app.set_active_profile(tmp_path / "vga.toml")
        # State cambio al nuevo perfil (no se revierte).
        assert app.backend_path == tmp_path / "vga.toml"
        # Manifest apunta al nuevo (write_active_profile si se completo).
        assert (
            AlacrittyBackend().read_active_profile(manifest)
            == tmp_path / "vga.toml"
        )
        # Warning toast con la hint custom.
        assert len(notifications) == 1
        msg, severity = notifications[0]
        assert "reload failed" in msg.lower()
        assert "Custom hint" in msg
        assert severity == "warning"
