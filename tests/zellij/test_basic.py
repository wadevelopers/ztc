"""Smoke tests del subpaquete ztc.zellij: import, assets accesibles,
parser KDL funciona end-to-end con un tema bundleado."""

from __future__ import annotations


def test_import_package() -> None:
    import ztc.zellij

    assert hasattr(ztc.zellij, "config")
    assert hasattr(ztc.zellij, "theme_assets")
    assert hasattr(ztc.zellij, "user_themes")
    assert ztc.zellij.TEXTUAL_FALLBACK == "textual-dark"


def test_bundled_theme_names_includes_known() -> None:
    from ztc.zellij.user_themes import builtin_theme_names

    names = builtin_theme_names()
    # Algunos clasicos que deberian estar.
    assert "dracula" in names
    assert "tokyo-night" in names
    assert "nord" in names
    # 'ansi' debe estar excluido.
    assert "ansi" not in names


def test_load_bundled_theme_returns_data() -> None:
    from ztc.zellij.theme_assets import load_bundled_theme

    theme = load_bundled_theme("dracula")
    assert theme is not None
    assert theme.name == "dracula"
    assert "text_unselected" in theme.components


def test_build_textual_theme_for_bundled() -> None:
    from ztc.zellij.theme_assets import build_textual_theme, load_bundled_theme

    bundled = load_bundled_theme("dracula")
    assert bundled is not None
    textual = build_textual_theme(bundled)
    assert textual is not None
    assert textual.name == "dracula"


def test_legacy_overrides_apply() -> None:
    """molokai-dark blue tiene override #3465a4 (configurado en
    LEGACY_THEME_OVERRIDES)."""
    from ztc.zellij.theme_assets import derive_legacy_slots_from_bundled

    slots = derive_legacy_slots_from_bundled("molokai-dark")
    assert slots is not None
    assert slots["blue"] == "#3465a4"


def test_read_active_theme_handles_missing(tmp_path) -> None:
    from ztc.zellij.config import read_active_theme

    assert read_active_theme(tmp_path / "missing.kdl") is None


def test_read_active_theme_finds_uncommented(tmp_path) -> None:
    from ztc.zellij.config import read_active_theme

    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        '// theme "comented"\ntheme "dracula"\n', encoding="utf-8"
    )
    assert read_active_theme(cfg) == "dracula"


def test_list_user_themes_parses_block(tmp_path) -> None:
    from ztc.zellij.user_themes import list_user_themes

    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n    mio {\n        fg "#abcdef"\n        bg "#123456"\n    }\n}\n',
        encoding="utf-8",
    )
    user = list_user_themes(cfg)
    assert len(user) == 1
    assert user[0].name == "mio"
    assert user[0].source == "user"
    assert {c.name: c.value for c in user[0].colors} == {
        "fg": "#abcdef",
        "bg": "#123456",
    }
