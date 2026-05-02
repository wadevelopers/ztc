from __future__ import annotations

from datetime import datetime
from pathlib import Path

from term_config_tui.services import backups


def test_backup_path_uses_timestamp(tmp_path: Path) -> None:
    p = tmp_path / "config.kdl"
    when = datetime(2026, 5, 2, 15, 4, 7)
    out = backups.backup_path_for(p, now=when)
    assert out.name == "config.kdl.bak.20260502-150407"
    assert out.parent == p.parent


def test_make_backup_returns_none_if_missing(tmp_path: Path) -> None:
    assert backups.make_backup(tmp_path / "nope.kdl") is None


def test_make_backup_copies_contents(tmp_path: Path) -> None:
    p = tmp_path / "x.toml"
    p.write_text("hola", encoding="utf-8")
    when = datetime(2026, 5, 2, 12, 0, 0)
    backup = backups.make_backup(p, now=when)
    assert backup is not None
    assert backup.read_text(encoding="utf-8") == "hola"
    assert backup.name.startswith("x.toml.bak.")
