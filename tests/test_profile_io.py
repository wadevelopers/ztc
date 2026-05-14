"""Tests del helper `profile_io.validate_profile_path`."""

from __future__ import annotations

from pathlib import Path

from ztc.services.profile_io import (
    expected_extension,
    resolve_profile_path,
    validate_profile_path,
)
from ztc.services.terminals.alacritty import AlacrittyBackend
from ztc.services.terminals.kitty import KittyBackend

# ---------- expected_extension ----------


def test_expected_extension_alacritty() -> None:
    assert expected_extension(AlacrittyBackend()) == ".toml"


def test_expected_extension_kitty() -> None:
    assert expected_extension(KittyBackend()) == ".conf"


# ---------- resolve_profile_path ----------


def test_resolve_profile_path_relative(tmp_path: Path) -> None:
    assert resolve_profile_path("c64.toml", tmp_path) == tmp_path / "c64.toml"


def test_resolve_profile_path_absolute(tmp_path: Path) -> None:
    abs_path = tmp_path / "x" / "c64.toml"
    assert resolve_profile_path(str(abs_path), tmp_path) == abs_path


# ---------- validate_profile_path ----------


def test_validate_rejects_wrong_extension(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    error = validate_profile_path(backend, tmp_path / "x.conf")
    assert error is not None
    assert ".toml" in error


def test_validate_rejects_missing_parent_dir(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    error = validate_profile_path(backend, tmp_path / "nope" / "x.toml")
    assert error is not None
    assert "Directory does not exist" in error


def test_validate_accepts_valid_path(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    assert validate_profile_path(backend, tmp_path / "c64.toml") is None


def test_validate_rejects_manifest_path(tmp_path: Path) -> None:
    """Manifest_path no puede ser usado como nombre de perfil. Sin este
    guard, Save-as al manifest sobrescribiria managed directives y
    crearia auto-referencia (`include kitty.conf` dentro de
    `kitty.conf`) → recursion infinita al reload."""
    backend = KittyBackend()
    manifest = tmp_path / "kitty.conf"
    error = validate_profile_path(backend, manifest, manifest_path=manifest)
    assert error is not None
    assert "manifest" in error.lower()
    assert manifest.name in error


def test_validate_accepts_path_different_from_manifest(tmp_path: Path) -> None:
    backend = KittyBackend()
    assert (
        validate_profile_path(
            backend,
            tmp_path / "c64.conf",
            manifest_path=tmp_path / "kitty.conf",
        )
        is None
    )


def test_validate_rejects_forbidden_path(tmp_path: Path) -> None:
    """Caso edge Load+G2: el nombre del primer perfil no puede coincidir
    con el target del Load."""
    backend = AlacrittyBackend()
    target = tmp_path / "c64.toml"
    error = validate_profile_path(backend, target, forbidden_path=target)
    assert error is not None
    assert "collides" in error.lower()


def test_validate_manifest_check_takes_precedence_over_forbidden(
    tmp_path: Path,
) -> None:
    """Si path == manifest_path == forbidden_path, prioriza el mensaje de
    manifest (mas informativo: explica el problema raiz)."""
    backend = KittyBackend()
    target = tmp_path / "kitty.conf"
    error = validate_profile_path(
        backend, target, manifest_path=target, forbidden_path=target
    )
    assert error is not None
    assert "manifest" in error.lower()
