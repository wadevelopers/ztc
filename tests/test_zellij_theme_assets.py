from __future__ import annotations

from term_config_tui.services import zellij_theme_assets as zta


def test_list_bundled_theme_names_returns_dozens() -> None:
    names = zta.list_bundled_theme_names()
    # Vendorizamos los .kdl del repo oficial; deberian ser 30+.
    assert len(names) >= 30
    assert "dracula" in names
    assert "tokyo-night" in names
    assert "gruber-darker" in names


def test_load_dracula_has_expected_components() -> None:
    theme = zta.load_bundled_theme("dracula")
    assert theme is not None
    assert theme.name == "dracula"
    assert "text_unselected" in theme.components
    assert "text_selected" in theme.components
    assert "ribbon_selected" in theme.components
    # text_selected.background es la BG real del tema (#282a36 dracula).
    assert theme.components["text_selected"].background == "#282a36"


def test_load_unknown_returns_none() -> None:
    assert zta.load_bundled_theme("does-not-exist") is None


def test_build_textual_theme_dracula() -> None:
    z = zta.load_bundled_theme("dracula")
    theme = zta.build_textual_theme(z)
    assert theme is not None
    assert theme.name == "dracula"
    assert theme.background == "#282a36"  # bg real
    assert theme.foreground == "#ffffff"
    assert theme.primary == "#50fa7b"  # iconic dracula green (ribbon_selected.bg)
    assert theme.dark is True


def test_build_textual_theme_catppuccin_latte_marks_light() -> None:
    z = zta.load_bundled_theme("catppuccin-latte")
    theme = zta.build_textual_theme(z)
    assert theme is not None
    # latte tiene bg claro ~ #dce0e8 -> dark=False.
    assert theme.dark is False
    assert theme.background == "#dce0e8"


def test_build_textual_theme_returns_none_for_invalid() -> None:
    bogus = zta.ZellijUITheme(name="bogus", components={})
    assert zta.build_textual_theme(bogus) is None


def test_build_textual_theme_from_legacy_basic() -> None:
    theme = zta.build_textual_theme_from_legacy(
        "my-theme",
        {
            "fg": "#cdd6f4",
            "bg": "#1e1e2e",
            "blue": "#89b4fa",
            "red": "#f38ba8",
            "green": "#a6e3a1",
            "yellow": "#f9e2af",
            "cyan": "#94e2d5",
        },
    )
    assert theme is not None
    assert theme.name == "my-theme"
    assert theme.foreground == "#cdd6f4"
    assert theme.background == "#1e1e2e"
    assert theme.primary == "#89b4fa"
    assert theme.error == "#f38ba8"
    assert theme.success == "#a6e3a1"
    assert theme.warning == "#f9e2af"
    assert theme.accent == "#94e2d5"
    assert theme.dark is True


def test_build_textual_theme_from_legacy_missing_fg_or_bg_returns_none() -> None:
    assert zta.build_textual_theme_from_legacy("x", {"fg": "#fff"}) is None
    assert zta.build_textual_theme_from_legacy("x", {"bg": "#000"}) is None


def test_all_bundled_themes_build_valid_textual_themes() -> None:
    """Todos los .kdl vendorizados (excepto 'ansi') deben construir un
    Textual Theme valido. 'ansi' usa indices de paleta del terminal,
    no RGB, asi que no podemos construir un Theme sin saber la paleta.
    """
    failures: list[str] = []
    for ui in zta.load_all_bundled_themes():
        if ui.name == "ansi":
            continue
        theme = zta.build_textual_theme(ui)
        if theme is None:
            failures.append(ui.name)
    assert failures == [], f"Build fallo para: {failures}"
