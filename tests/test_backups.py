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


def test_make_backup_rotates_keeping_latest_5(tmp_path: Path) -> None:
    """Al crear un backup nuevo, solo se conservan los KEEP_BACKUPS=5
    mas recientes (por timestamp en el nombre)."""
    p = tmp_path / "config.kdl"
    p.write_text("v0", encoding="utf-8")
    # 7 backups con timestamps crecientes.
    for i in range(7):
        p.write_text(f"v{i}", encoding="utf-8")
        backups.make_backup(p, now=datetime(2026, 5, 2, 12, i, 0))
    remaining = backups.list_backups(p)
    assert len(remaining) == backups.KEEP_BACKUPS
    # Los conservados son los 5 mas recientes (minuto 6 al 2).
    minutes = [b.name.split(".bak.")[1] for b in remaining]
    assert minutes == [
        "20260502-120600",
        "20260502-120500",
        "20260502-120400",
        "20260502-120300",
        "20260502-120200",
    ]


def test_prune_old_backups_no_op_when_under_limit(tmp_path: Path) -> None:
    p = tmp_path / "config.kdl"
    p.write_text("v0", encoding="utf-8")
    for i in range(3):
        p.write_text(f"v{i}", encoding="utf-8")
        backups.make_backup(p, now=datetime(2026, 5, 2, 12, i, 0))
    assert backups.prune_old_backups(p) == []
    assert len(backups.list_backups(p)) == 3
