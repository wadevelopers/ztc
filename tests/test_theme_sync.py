from __future__ import annotations

import shutil
from pathlib import Path

from term_config_tui.services import alacritty, theme_sync, toml_io

ALA_FIX = Path(__file__).parent / "fixtures" / "alacritty"


def _make_alacritty(tmp_path: Path) -> Path:
    dst = tmp_path / "alacritty.toml"
    shutil.copy2(ALA_FIX / "alacritty_min.toml", dst)
    return dst


def _empty_zellij_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    return cfg


def test_sync_from_bundled_dracula(tmp_path: Path) -> None:
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    result = theme_sync.sync_alacritty_with_zellij_theme(
        zellij_theme_name="dracula",
        alacritty_path=ala,
        zellij_config_path=cfg,
    )
    assert result.skipped_reason is None
    assert result.backup is not None
    doc = toml_io.load_toml(ala)
    # Mapping 1:1 Paleta ANSI -> Alacritty. fg <- ribbon_un.background
    # (#f8f8f2 en dracula); white <- text_un.base (#ffffff).
    assert alacritty.read_slot(doc, "primary", "background") == "#000000"
    assert alacritty.read_slot(doc, "primary", "foreground") == "#f8f8f2"
    assert alacritty.read_slot(doc, "normal", "white") == "#ffffff"
    assert alacritty.read_slot(doc, "normal", "red") == "#ff5555"


def test_sync_from_user_theme(tmp_path: Path) -> None:
    ala = _make_alacritty(tmp_path)
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n'
        '    mio {\n'
        '        fg "#abcdef"\n'
        '        bg "#123456"\n'
        '        white "#dddddd"\n'
        '        red "#ff0000"\n'
        '        green "#00ff00"\n'
        '    }\n'
        '}\n',
        encoding="utf-8",
    )
    result = theme_sync.sync_alacritty_with_zellij_theme(
        zellij_theme_name="mio",
        alacritty_path=ala,
        zellij_config_path=cfg,
    )
    assert result.skipped_reason is None
    doc = toml_io.load_toml(ala)
    assert alacritty.read_slot(doc, "primary", "background") == "#123456"
    # Mapping 1:1: primary.foreground <- legacy fg.
    assert alacritty.read_slot(doc, "primary", "foreground") == "#abcdef"
    assert alacritty.read_slot(doc, "normal", "white") == "#dddddd"
    assert alacritty.read_slot(doc, "normal", "red") == "#ff0000"
    assert alacritty.read_slot(doc, "normal", "green") == "#00ff00"


def test_sync_only_writes_changed_slots(tmp_path: Path) -> None:
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    # Pre-set primary.background al MISMO valor que pondria dracula
    # (sin override, bg = text_unselected.background = #000000).
    doc = toml_io.load_toml(ala)
    alacritty.write_slot(doc, "primary", "background", "#000000")
    toml_io.dump_toml(doc, ala, backup=False)

    result = theme_sync.sync_alacritty_with_zellij_theme(
        zellij_theme_name="dracula",
        alacritty_path=ala,
        zellij_config_path=cfg,
    )
    # Aunque haya otros slots a actualizar, primary.background NO debe estar
    # en la lista de updated (ya estaba con el valor correcto).
    assert ("primary", "background") not in result.updated
    # Pero otros si.
    assert ("primary", "foreground") in result.updated


def test_sync_no_alacritty_file(tmp_path: Path) -> None:
    cfg = _empty_zellij_config(tmp_path)
    ala = tmp_path / "no.toml"
    result = theme_sync.sync_alacritty_with_zellij_theme(
        zellij_theme_name="dracula",
        alacritty_path=ala,
        zellij_config_path=cfg,
    )
    assert result.skipped_reason and "No existe" in result.skipped_reason
    assert not result.updated


def test_sync_unknown_theme(tmp_path: Path) -> None:
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    result = theme_sync.sync_alacritty_with_zellij_theme(
        zellij_theme_name="nonexistent-theme-name",
        alacritty_path=ala,
        zellij_config_path=cfg,
    )
    assert result.skipped_reason and "sin colores" in result.skipped_reason
    assert not result.updated


def test_sync_no_changes_returns_no_backup(tmp_path: Path) -> None:
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    # Aplicar dracula una vez.
    theme_sync.sync_alacritty_with_zellij_theme(
        zellij_theme_name="dracula",
        alacritty_path=ala,
        zellij_config_path=cfg,
    )
    # Aplicar de nuevo: nada deberia cambiar.
    result = theme_sync.sync_alacritty_with_zellij_theme(
        zellij_theme_name="dracula",
        alacritty_path=ala,
        zellij_config_path=cfg,
    )
    assert result.backup is None
    assert result.updated == {}
    assert result.skipped_reason == "Sin cambios"


def test_sync_propagates_text_selected_to_alacritty_selection(tmp_path: Path) -> None:
    """El bg/text de la seleccion en alacritty se sincroniza desde
    text_selected.{background,base} del .kdl Zellij."""
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    # ayu-dark tiene text_selected.background = #475266 y .base = #cccac2.
    theme_sync.sync_alacritty_with_zellij_theme(
        zellij_theme_name="ayu-dark",
        alacritty_path=ala,
        zellij_config_path=cfg,
    )
    doc = toml_io.load_toml(ala)
    assert alacritty.read_slot(doc, "selection", "background") == "#475266"
    assert alacritty.read_slot(doc, "selection", "text") == "#cccac2"


def test_sync_user_theme_with_rich_components(tmp_path: Path) -> None:
    """Si un user theme tiene raw_components, sus text_selected.* van
    a alacritty.selection.*."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n'
        '    mio {\n'
        '        fg "#aaaaaa"\n'
        '        bg "#111111"\n'
        '        text_selected {\n'
        '            base "#ffffff"\n'
        '            background "#5566aa"\n'
        '        }\n'
        '    }\n'
        '}\n',
        encoding="utf-8",
    )
    ala = _make_alacritty(tmp_path)
    theme_sync.sync_alacritty_with_zellij_theme(
        zellij_theme_name="mio",
        alacritty_path=ala,
        zellij_config_path=cfg,
    )
    doc = toml_io.load_toml(ala)
    assert alacritty.read_slot(doc, "selection", "background") == "#5566aa"
    assert alacritty.read_slot(doc, "selection", "text") == "#ffffff"


def test_sync_preserves_other_alacritty_sections(tmp_path: Path) -> None:
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    theme_sync.sync_alacritty_with_zellij_theme(
        zellij_theme_name="dracula",
        alacritty_path=ala,
        zellij_config_path=cfg,
    )
    text = ala.read_text(encoding="utf-8")
    # Las secciones que no son colors no se tocan.
    assert "[window]" in text
    assert "padding" in text
    assert "opacity" in text
