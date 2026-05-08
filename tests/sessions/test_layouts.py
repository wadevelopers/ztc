"""Tests del listado de layouts y de la lectura de `default_layout` desde config.kdl."""

from __future__ import annotations

from pathlib import Path

from ztc.sessions.services import layouts


def test_list_layout_files(tmp_path: Path) -> None:
    (tmp_path / "dev.kdl").write_text("layout {}\n")
    (tmp_path / "work.kdl").write_text("layout {}\n")
    (tmp_path / "ignore.txt").write_text("not a layout\n")
    assert layouts.list_layout_files(tmp_path) == ["dev", "work"]


def test_list_layout_files_missing_dir(tmp_path: Path) -> None:
    assert layouts.list_layout_files(tmp_path / "no-existe") == []


def test_zellij_default_layout_reads_value(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        '// comentario\n'
        'theme "ayu-dark"\n'
        'default_layout "dev"\n'
        '// otra cosa\n',
        encoding="utf-8",
    )
    assert layouts.zellij_default_layout(cfg) == "dev"


def test_zellij_default_layout_missing(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text('theme "ayu-dark"\n', encoding="utf-8")
    assert layouts.zellij_default_layout(cfg) is None


def test_zellij_default_layout_no_file(tmp_path: Path) -> None:
    assert layouts.zellij_default_layout(tmp_path / "no.kdl") is None
