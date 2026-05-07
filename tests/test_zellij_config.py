from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ztc.services import zellij_config

FIX = Path(__file__).parent / "fixtures" / "zellij"


def _copy(src: Path, dst_dir: Path) -> Path:
    dst = dst_dir / src.name
    shutil.copy2(src, dst)
    return dst


def test_read_active_theme(tmp_path: Path) -> None:
    cfg = _copy(FIX / "config_with_theme.kdl", tmp_path)
    assert zellij_config.read_active_theme(cfg) == "custom_dark"


def test_read_active_theme_returns_none_if_only_commented(tmp_path: Path) -> None:
    cfg = _copy(FIX / "config_no_theme.kdl", tmp_path)
    assert zellij_config.read_active_theme(cfg) is None


def test_set_active_theme_replaces_only_target_line(tmp_path: Path) -> None:
    cfg = _copy(FIX / "config_with_theme.kdl", tmp_path)
    original = cfg.read_text(encoding="utf-8")

    backup = zellij_config.set_active_theme(cfg, "dracula")

    new = cfg.read_text(encoding="utf-8")
    assert 'theme "dracula"' in new
    assert 'theme "custom_dark"' not in new
    # Las lineas comentadas y el resto del archivo se preservan.
    assert '// theme "dracula"' in new
    assert "keybinds {" in new
    assert 'default_mode "normal"' in new
    # Backup creado y contiene el original.
    assert backup is not None
    assert backup.read_text(encoding="utf-8") == original


def test_set_active_theme_inserts_when_missing(tmp_path: Path) -> None:
    cfg = _copy(FIX / "config_no_theme.kdl", tmp_path)
    zellij_config.set_active_theme(cfg, "dracula")
    new = cfg.read_text(encoding="utf-8")
    assert new.endswith('theme "dracula"\n')
    # Lo previo se preserva.
    assert "keybinds {" in new
    assert "// theme \"dracula\"" in new


def test_set_active_theme_rejects_invalid_name(tmp_path: Path) -> None:
    cfg = _copy(FIX / "config_with_theme.kdl", tmp_path)
    with pytest.raises(ValueError):
        zellij_config.set_active_theme(cfg, 'evil"name')
    # No debe haber tocado el archivo.
    assert 'theme "custom_dark"' in cfg.read_text(encoding="utf-8")


def test_set_active_theme_indented_line(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text('   theme "old"\n', encoding="utf-8")
    zellij_config.set_active_theme(cfg, "new", backup=False)
    assert cfg.read_text(encoding="utf-8") == '   theme "new"\n'


def test_list_layouts_orders_by_name(tmp_path: Path) -> None:
    layouts_dir = tmp_path / "layouts"
    layouts_dir.mkdir()
    shutil.copy2(FIX / "layout_simple.kdl", layouts_dir / "b.kdl")
    shutil.copy2(FIX / "layout_simple.kdl", layouts_dir / "a.kdl")
    layouts = zellij_config.list_layouts(layouts_dir)
    assert [layout.name for layout in layouts] == ["a", "b"]


def test_list_layouts_empty_dir(tmp_path: Path) -> None:
    assert zellij_config.list_layouts(tmp_path / "nope") == []
