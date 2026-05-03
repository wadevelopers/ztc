"""Tests del CRUD de user themes (splice del bloque themes)."""

from __future__ import annotations

from pathlib import Path

import pytest

from term_config_tui.models.theme import ZellijColor, ZellijTheme
from term_config_tui.services import zellij_themes


def test_is_valid_theme_name() -> None:
    assert zellij_themes.is_valid_theme_name("dracula")
    assert zellij_themes.is_valid_theme_name("custom_dark")
    assert zellij_themes.is_valid_theme_name("my-theme-2")
    assert not zellij_themes.is_valid_theme_name("2bad")  # empieza por digito
    assert not zellij_themes.is_valid_theme_name("with space")
    assert not zellij_themes.is_valid_theme_name("")


def test_find_themes_block_handles_nested_braces() -> None:
    text = (
        "keybinds {}\n"
        "themes {\n"
        '    a {\n        fg "#fff"\n    }\n'
        '    b {\n'
        '        bg "#000"\n'
        "    }\n"
        "}\n"
        'theme "a"\n'
    )
    rng = zellij_themes.find_themes_block(text)
    assert rng is not None
    start, end = rng
    block = text[start:end]
    assert block.startswith("themes {")
    assert block.endswith("}")
    assert 'fg "#fff"' in block
    assert 'theme "a"' not in block  # no debe extenderse


def test_find_themes_block_returns_none_when_missing() -> None:
    assert zellij_themes.find_themes_block("// no themes here\n") is None


def test_find_themes_block_handles_brace_in_string() -> None:
    text = 'themes {\n    a { fg "#}{ raro }" }\n}\n'
    rng = zellij_themes.find_themes_block(text)
    assert rng is not None
    start, end = rng
    assert text[start:end].endswith("}")
    # Y solo el bloque themes, sin texto extra.
    assert text[end:].strip() == ""


def test_render_themes_block_format() -> None:
    themes = [
        ZellijTheme(
            name="t1",
            source="user",
            colors=[ZellijColor("fg", "#fff"), ZellijColor("bg", "#000")],
        )
    ]
    text = zellij_themes.render_themes_block(themes)
    assert text == 'themes {\n    t1 {\n        fg "#fff"\n        bg "#000"\n    }\n}'


def test_save_user_themes_replaces_existing_block(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        '// header\n'
        'keybinds {\n    normal {}\n}\n'
        'themes {\n'
        '    old {\n        fg "#ff0000"\n    }\n'
        '}\n'
        'theme "old"\n',
        encoding="utf-8",
    )
    new = [
        ZellijTheme(
            name="new",
            source="user",
            colors=[ZellijColor("fg", "#abcdef"), ZellijColor("bg", "#111111")],
        )
    ]
    backup = zellij_themes.save_user_themes(cfg, new)
    text = cfg.read_text(encoding="utf-8")
    # Bloque viejo desaparece, bloque nuevo presente.
    assert "old {" not in text
    assert "new {" in text
    assert 'fg "#abcdef"' in text
    # Resto preservado.
    assert "// header" in text
    assert "keybinds {" in text
    assert 'theme "old"' in text  # la directiva es ortogonal al bloque
    # Backup creado.
    assert backup is not None and backup.exists()


def test_save_user_themes_appends_when_no_block(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text("default_mode \"normal\"\n", encoding="utf-8")
    themes = [
        ZellijTheme(
            name="t",
            source="user",
            colors=[ZellijColor("bg", "#000000")],
        )
    ]
    zellij_themes.save_user_themes(cfg, themes)
    text = cfg.read_text(encoding="utf-8")
    assert text.startswith('default_mode "normal"')
    assert "themes {" in text
    assert "t {" in text


def test_save_user_themes_empty_list_removes_block(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'keybinds {}\n\nthemes {\n    a {\n        fg "#000"\n    }\n}\n\ndefault_mode "normal"\n',
        encoding="utf-8",
    )
    zellij_themes.save_user_themes(cfg, [])
    text = cfg.read_text(encoding="utf-8")
    assert "themes {" not in text
    assert "keybinds {}" in text
    assert 'default_mode "normal"' in text


def test_upsert_user_theme_adds_then_updates(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    zellij_themes.upsert_user_theme(
        cfg,
        ZellijTheme(name="a", source="user", colors=[ZellijColor("fg", "#111")]),
    )
    themes = zellij_themes.list_user_themes(cfg)
    assert [t.name for t in themes] == ["a"]
    # Update: cambiar el color.
    zellij_themes.upsert_user_theme(
        cfg,
        ZellijTheme(name="a", source="user", colors=[ZellijColor("fg", "#222")]),
    )
    themes = zellij_themes.list_user_themes(cfg)
    assert themes[0].colors[0].value == "#222"


def test_delete_user_theme_removes_only_target(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n'
        '    a {\n        fg "#000"\n    }\n'
        '    b {\n        fg "#fff"\n    }\n'
        '}\n',
        encoding="utf-8",
    )
    zellij_themes.delete_user_theme(cfg, "a")
    themes = zellij_themes.list_user_themes(cfg)
    assert [t.name for t in themes] == ["b"]


def test_delete_user_theme_no_op_when_missing(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n    a {\n        fg "#000"\n    }\n}\n',
        encoding="utf-8",
    )
    backup = zellij_themes.delete_user_theme(cfg, "nope")
    assert backup is None  # no se hizo escritura


def test_clone_user_theme_copies_colors(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n    src {\n        fg "#abc"\n    }\n}\n',
        encoding="utf-8",
    )
    zellij_themes.clone_theme(cfg, "src", "dst")
    themes = {t.name: t for t in zellij_themes.list_user_themes(cfg)}
    assert "dst" in themes
    assert themes["dst"].colors[0].value == "#abc"


def test_clone_builtin_extracts_colors_from_bundled(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    # 'dracula' es built-in vendorizado: clonar deberia extraer slots
    # legacy desde los componentes UI del .kdl bundled.
    zellij_themes.clone_theme(cfg, "dracula", "my-dracula")
    themes = zellij_themes.list_user_themes(cfg)
    assert themes[0].name == "my-dracula"
    by_name = {c.name: c.value for c in themes[0].colors}
    assert list(by_name.keys()) == list(zellij_themes.LEGACY_SLOTS)
    # fg de dracula es text_unselected.base = #ffffff.
    assert by_name["fg"] == "#ffffff"
    # bg de dracula es text_selected.background = #282a36.
    assert by_name["bg"] == "#282a36"
    # red derivado de exit_code_error.base = #ff5555.
    assert by_name["red"] == "#ff5555"


def test_clone_ayu_dark_bg_is_text_unselected(tmp_path: Path) -> None:
    """Regresion: ayu-dark stores el bg real en text_unselected.background
    (#131721), no en text_selected.background (#475266 = pane seleccionado)."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    zellij_themes.clone_theme(cfg, "ayu-dark", "my-ayu")
    by_name = {c.name: c.value for c in zellij_themes.list_user_themes(cfg)[0].colors}
    assert by_name["bg"] == "#131721"


def test_clone_unknown_uses_black_defaults(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    # Theme name desconocido (no built-in, no user) -> defaults #000000.
    zellij_themes.clone_theme(cfg, "totally-fake-theme", "copy")
    themes = zellij_themes.list_user_themes(cfg)
    assert themes[0].colors[0].value == "#000000"


def test_clone_rejects_existing_name(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n    foo {\n        fg "#000"\n    }\n}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        zellij_themes.clone_theme(cfg, "foo", "foo")


def test_clone_rejects_invalid_name(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    with pytest.raises(ValueError):
        zellij_themes.clone_theme(cfg, "dracula", "1invalid")


def test_default_legacy_slots() -> None:
    slots = zellij_themes.default_legacy_slots()
    assert [s.name for s in slots] == list(zellij_themes.LEGACY_SLOTS)
    assert all(s.value.startswith("#") for s in slots)
