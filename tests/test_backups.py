from __future__ import annotations

from pathlib import Path

from ztc.services import backups


def test_backup_path_uses_content_hash(tmp_path: Path) -> None:
    """Formato: `<name>.<hash8>.bak`. El sufijo `.bak` queda al final
    (filtros `*.bak` lo agarran). La fecha/hora NO está en el nombre."""
    p = tmp_path / "config.kdl"
    p.write_text("hola mundo", encoding="utf-8")
    out = backups.backup_path_for(p)
    assert out.suffix == ".bak"
    assert out.name.startswith("config.kdl.")
    assert out.name.endswith(".bak")
    # El segmento de hash debe ser hex de 8 chars.
    hash_part = out.stem.removeprefix("config.kdl.")
    assert len(hash_part) == 8
    assert all(c in "0123456789abcdef" for c in hash_part)
    assert out.parent == p.parent


def test_backup_path_deterministic_for_same_content(tmp_path: Path) -> None:
    """Mismo contenido → mismo hash → mismo path. Es la base de la
    idempotencia."""
    p = tmp_path / "config.kdl"
    p.write_text("hola", encoding="utf-8")
    out1 = backups.backup_path_for(p)
    out2 = backups.backup_path_for(p)
    assert out1 == out2


def test_make_backup_returns_none_if_missing(tmp_path: Path) -> None:
    assert backups.make_backup(tmp_path / "nope.kdl") is None


def test_make_backup_copies_contents(tmp_path: Path) -> None:
    p = tmp_path / "x.toml"
    p.write_text("hola", encoding="utf-8")
    backup = backups.make_backup(p)
    assert backup is not None
    assert backup.read_text(encoding="utf-8") == "hola"
    assert backup.suffix == ".bak"


def test_make_backup_idempotent_when_content_unchanged(tmp_path: Path) -> None:
    """Si el contenido no cambió desde el último backup, no se crea
    duplicado — retorna el path existente."""
    p = tmp_path / "x.toml"
    p.write_text("v0", encoding="utf-8")
    first = backups.make_backup(p)
    assert first is not None
    second = backups.make_backup(p)
    assert second == first
    # Solo hay 1 backup en disco.
    assert len(list(tmp_path.glob("x.toml.*.bak"))) == 1


def test_make_backup_rotates_keeping_latest_5(tmp_path: Path) -> None:
    """Al crear un backup nuevo, solo se conservan los KEEP_BACKUPS=5
    mas recientes por `mtime`. `make_backup` setea mtime con resolucion
    de ns, garantizando orden estricto incluso con saves consecutivos."""
    p = tmp_path / "config.kdl"
    # 7 backups con contenidos distintos (cada uno genera hash distinto).
    for i in range(7):
        p.write_text(f"v{i}", encoding="utf-8")
        backup = backups.make_backup(p)
        assert backup is not None
    remaining = backups.list_backups(p)
    assert len(remaining) == backups.KEEP_BACKUPS
    # Los conservados son los 5 mas recientes (contenidos v2..v6); v0 y
    # v1 quedaron afuera.
    contents = {b.read_text(encoding="utf-8") for b in remaining}
    assert contents == {"v2", "v3", "v4", "v5", "v6"}


def test_prune_old_backups_no_op_when_under_limit(tmp_path: Path) -> None:
    p = tmp_path / "config.kdl"
    p.write_text("v0", encoding="utf-8")
    for i in range(3):
        p.write_text(f"v{i}", encoding="utf-8")
        backups.make_backup(p)
    assert backups.prune_old_backups(p) == []
    assert len(backups.list_backups(p)) == 3
