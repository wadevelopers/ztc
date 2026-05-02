from __future__ import annotations

from pathlib import Path

from term_config_tui.services import zellij_themes

FIX = Path(__file__).parent / "fixtures" / "zellij"


def test_builtin_list_includes_known_names() -> None:
    names = {t.name for t in zellij_themes.list_builtin_themes()}
    for expected in ("dracula", "tokyo-night", "catppuccin-mocha", "default"):
        assert expected in names


def test_builtin_themes_have_no_duplicates_and_are_sorted() -> None:
    names = [t.name for t in zellij_themes.list_builtin_themes()]
    assert names == sorted(names)
    assert len(names) == len(set(names))


def test_list_user_themes_parses_block() -> None:
    themes = zellij_themes.list_user_themes(FIX / "config_with_user_themes.kdl")
    by_name = {t.name: t for t in themes}
    assert set(by_name.keys()) == {"custom_dark", "midnight"}

    cd = by_name["custom_dark"]
    assert cd.is_user
    color_map = {c.name: c.value for c in cd.colors}
    assert color_map["fg"] == "#cdd6f4"
    assert color_map["bg"] == "#585b70"
    assert color_map["red"] == "#d5597c"


def test_list_user_themes_handles_missing_file(tmp_path: Path) -> None:
    assert zellij_themes.list_user_themes(tmp_path / "nope.kdl") == []


def test_list_user_themes_handles_no_themes_block() -> None:
    assert zellij_themes.list_user_themes(FIX / "config_with_theme.kdl") == []


def test_list_all_themes_user_first_then_builtins() -> None:
    themes = zellij_themes.list_all_themes(FIX / "config_with_user_themes.kdl")
    user_count = sum(1 for t in themes if t.is_user)
    assert user_count == 2
    # Los primeros dos deben ser user themes (ordenados antes de builtins).
    assert themes[0].is_user and themes[1].is_user
    # Y a continuacion built-ins, sin duplicados.
    builtins = [t.name for t in themes if not t.is_user]
    assert "dracula" in builtins
    assert len(builtins) == len(set(builtins))


def test_list_all_themes_user_overrides_builtin_name(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n    dracula {\n        fg "#fff"\n    }\n}\n',
        encoding="utf-8",
    )
    themes = zellij_themes.list_all_themes(cfg)
    drac = [t for t in themes if t.name == "dracula"]
    assert len(drac) == 1
    assert drac[0].is_user  # el usuario gana
