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
    # 'dracula' es built-in vendorizado: clonar extrae slots legacy
    # desde los componentes UI del .kdl bundled aplicando la regla unica.
    zellij_themes.clone_theme(cfg, "dracula", "my-dracula")
    themes = zellij_themes.list_user_themes(cfg)
    assert themes[0].name == "my-dracula"
    by_name = {c.name: c.value for c in themes[0].colors}
    assert list(by_name.keys()) == list(zellij_themes.LEGACY_SLOTS)
    # fg de dracula = text_unselected.base = #ffffff.
    assert by_name["fg"] == "#ffffff"
    # bg de dracula = text_unselected.background = #000000 (sin override).
    assert by_name["bg"] == "#000000"
    # red = exit_code_error.base = #ff5555.
    assert by_name["red"] == "#ff5555"


def test_clone_ayu_dark_bg_is_text_unselected(tmp_path: Path) -> None:
    """Regresion: ayu-dark stores el bg real en text_unselected.background
    (#131721), no en text_selected.background (#475266 = pane seleccionado)."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    zellij_themes.clone_theme(cfg, "ayu-dark", "my-ayu")
    by_name = {c.name: c.value for c in zellij_themes.list_user_themes(cfg)[0].colors}
    assert by_name["bg"] == "#131721"


def test_clone_active_theme_overlays_alacritty(tmp_path: Path) -> None:
    """Cuando se clona el tema activo y hay alacritty.toml, los slots
    actuales de alacritty deben pisar a los derivados del .kdl."""
    # Configurar: tema activo = dracula.
    cfg = tmp_path / "config.kdl"
    cfg.write_text('theme "dracula"\n', encoding="utf-8")

    # Alacritty con valores tweakeados (distintos al derivado de dracula).
    ala = tmp_path / "alacritty.toml"
    ala.write_text(
        "[colors.primary]\n"
        'background = "#222222"\n'
        'foreground = "#eeeeee"\n'
        "\n[colors.normal]\n"
        'red = "#ff0000"\n'
        'green = "#00ff00"\n',
        encoding="utf-8",
    )

    zellij_themes.clone_theme(cfg, "dracula", "my-dracula", alacritty_path=ala)
    by_name = {
        c.name: c.value for c in zellij_themes.list_user_themes(cfg)[0].colors
    }
    # Los slots presentes en alacritty se overlayan (pisan).
    assert by_name["bg"] == "#222222"
    assert by_name["fg"] == "#eeeeee"
    assert by_name["red"] == "#ff0000"
    assert by_name["green"] == "#00ff00"
    # Los slots NO presentes en alacritty quedan del derivado del .kdl.
    # 'orange' no esta en alacritty -> debe venir del .kdl de dracula.
    assert by_name["orange"] != "#000000"


def test_clone_non_active_theme_ignores_alacritty(tmp_path: Path) -> None:
    """Si se clona un tema que NO es el activo, alacritty no aplica
    porque alacritty representa OTRO tema en ese momento."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text('theme "dracula"\n', encoding="utf-8")
    ala = tmp_path / "alacritty.toml"
    ala.write_text(
        "[colors.primary]\n"
        'background = "#222222"\n'
        'foreground = "#eeeeee"\n',
        encoding="utf-8",
    )
    # Cloneamos tokyo-night (NO es el activo).
    zellij_themes.clone_theme(cfg, "tokyo-night", "my-tn", alacritty_path=ala)
    by_name = {
        c.name: c.value for c in zellij_themes.list_user_themes(cfg)[0].colors
    }
    # Debe coger los del .kdl de tokyo-night, NO los de alacritty.
    assert by_name["bg"] != "#222222"
    assert by_name["fg"] != "#eeeeee"


def test_clone_active_user_theme_overlays_alacritty(tmp_path: Path) -> None:
    """El overlay tambien aplica cuando el activo es un user theme."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n    mio {\n        fg "#aaaaaa"\n        bg "#111111"\n    }\n}\n'
        'theme "mio"\n',
        encoding="utf-8",
    )
    ala = tmp_path / "alacritty.toml"
    ala.write_text(
        '[colors.primary]\nbackground = "#222222"\nforeground = "#eeeeee"\n',
        encoding="utf-8",
    )
    zellij_themes.clone_theme(cfg, "mio", "mio-copia", alacritty_path=ala)
    themes = zellij_themes.list_user_themes(cfg)
    clone = next(t for t in themes if t.name == "mio-copia")
    by_name = {c.name: c.value for c in clone.colors}
    assert by_name["bg"] == "#222222"
    assert by_name["fg"] == "#eeeeee"


def test_clone_without_alacritty_path_uses_kdl_only(tmp_path: Path) -> None:
    """Sin alacritty_path, comportamiento clasico: solo .kdl."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text('theme "dracula"\n', encoding="utf-8")
    zellij_themes.clone_theme(cfg, "dracula", "my-dracula")
    by_name = {
        c.name: c.value for c in zellij_themes.list_user_themes(cfg)[0].colors
    }
    # Sin override de dracula bg, queda como text_unselected.background = #000000.
    assert by_name["bg"] == "#000000"
    assert by_name["fg"] == "#ffffff"


def test_clone_builtin_preserves_rich_components(tmp_path: Path) -> None:
    """Al clonar un built-in, los componentes del formato nuevo
    (text_unselected, ribbon_selected, etc.) se copian al user theme.
    Asi el clon renderiza igual que el original en Zellij UI."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    zellij_themes.clone_theme(cfg, "molokai-dark", "my-molokai")

    text = cfg.read_text(encoding="utf-8")
    # Componentes nuevo formato presentes.
    assert "text_unselected {" in text
    assert "ribbon_selected {" in text
    assert "exit_code_error {" in text
    # ribbon_selected.background de molokai (verde) debe estar.
    assert "0 140 0" in text
    # Y enteros no deben tener el sufijo .0 (kdl-py los emite como float).
    assert "255.0" not in text
    assert "255 255 255" in text


def test_clone_user_theme_preserves_rich_components(tmp_path: Path) -> None:
    """Si el src es un user theme con raw_components (clon previo de
    un built-in), el siguiente clon tambien los preserva."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    zellij_themes.clone_theme(cfg, "dracula", "my-dracula")
    zellij_themes.clone_theme(cfg, "my-dracula", "my-dracula-2")
    themes = {t.name: t for t in zellij_themes.list_user_themes(cfg)}
    assert "my-dracula-2" in themes
    # Debe tener los mismos componentes que el .kdl original.
    second = themes["my-dracula-2"]
    component_names = {rc.name for rc in second.raw_components}
    assert "text_unselected" in component_names
    assert "ribbon_selected" in component_names


def test_textual_theme_from_legacy_uses_rich_components_for_primary() -> None:
    """build_textual_theme_from_legacy usa ribbon_selected.background como
    primary cuando hay raw_components, en vez del slot legacy 'blue'."""
    from term_config_tui.services import zellij_theme_assets as zta

    # Para molokai: blue legacy = #66d9ef, pero ribbon_selected.bg = #008c00.
    # Si tenemos raw_components, primary debe ser #008c00 (no el blue).
    raw = zta.load_bundled_raw_components("molokai-dark")
    assert raw  # vendorizado
    th = zta.build_textual_theme_from_legacy(
        "my-molokai",
        {"fg": "#ffffff", "bg": "#000000", "blue": "#66d9ef"},
        raw_components=raw,
    )
    assert th is not None
    assert th.primary == "#008c00"  # del ribbon_selected.bg, no del blue
    assert th.foreground == "#ffffff"
    assert th.background == "#000000"


def test_textual_theme_from_legacy_falls_back_when_no_rich() -> None:
    """Sin raw_components, primary cae al slot legacy 'blue'."""
    from term_config_tui.services import zellij_theme_assets as zta

    th = zta.build_textual_theme_from_legacy(
        "x",
        {"fg": "#fff", "bg": "#000", "blue": "#66d9ef"},
        raw_components=None,
    )
    assert th is not None
    assert th.primary == "#66d9ef"


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
