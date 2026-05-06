from __future__ import annotations

import shutil
from pathlib import Path

from textual.widgets import OptionList

from term_config_tui.app import TermConfigApp
from term_config_tui.models.config import Paths
from term_config_tui.screens.theme_editor import ThemePickerScreen

FIX = Path(__file__).parent / "fixtures" / "zellij"


def _make_paths(tmp_path: Path, config_src: Path) -> Paths:
    cfg = tmp_path / "config.kdl"
    shutil.copy2(config_src, cfg)
    return Paths(
        zellij_config=cfg,
        zellij_layouts_dir=tmp_path / "layouts",
    )


def _make_app(tmp_path: Path, paths: Paths) -> TermConfigApp:
    """Crea TermConfigApp con backend_path apuntando al tmp para no
    tocar ~/.config/alacritty real."""
    return TermConfigApp(paths=paths, backend_path=tmp_path / "alacritty.toml")


async def test_theme_picker_lists_themes_and_marks_active(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path, FIX / "config_with_user_themes.kdl")
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThemePickerScreen)
        option_list = screen.query_one("#theme-list", OptionList)
        assert option_list.option_count > 5  # user themes + builtins

        # El tema activo aparece marcado con '*' en su label.
        labels = [
            option_list.get_option_at_index(i).prompt
            for i in range(option_list.option_count)
        ]
        active_label = next(label for label in labels if "custom_dark" in str(label))
        assert "*" in str(active_label)


async def test_app_registers_bundled_and_user_themes(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path, FIX / "config_with_user_themes.kdl")
    # El fixture define `custom_dark` y `midnight` como user themes con fg/bg.
    app = _make_app(tmp_path, paths)
    async with app.run_test() as _:
        # Built-in vendorizado registrado.
        assert "dracula" in app.available_themes
        assert "tokyo-night" in app.available_themes
        # User themes con fg/bg registrados con su nombre tal cual.
        assert "custom_dark" in app.available_themes
        assert "midnight" in app.available_themes


async def test_app_applies_active_zellij_theme_on_mount(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path, FIX / "config_with_user_themes.kdl")
    # config_with_user_themes tiene `theme "custom_dark"`.
    app = _make_app(tmp_path, paths)
    async with app.run_test() as _:
        assert app.theme == "custom_dark"


async def test_theme_picker_apply_changes_textual_theme(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path, FIX / "config_with_user_themes.kdl")
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("enter")  # menu -> Tema Zellij
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThemePickerScreen)
        option_list = screen.query_one("#theme-list", OptionList)
        target_index = next(
            i
            for i in range(option_list.option_count)
            if option_list.get_option_at_index(i).id == "dracula"
        )
        option_list.highlighted = target_index
        await pilot.pause()
        screen.action_apply()
        await pilot.pause()
        assert app.theme == "dracula"


async def test_theme_picker_apply_writes_config(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path, FIX / "config_with_user_themes.kdl")
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThemePickerScreen)
        option_list = screen.query_one("#theme-list", OptionList)

        target_index = next(
            i
            for i in range(option_list.option_count)
            if option_list.get_option_at_index(i).id == "dracula"
        )
        option_list.highlighted = target_index
        await pilot.pause()
        screen.action_apply()
        await pilot.pause()

        text = paths.zellij_config.read_text(encoding="utf-8")
        assert 'theme "dracula"' in text
        assert 'theme "custom_dark"' not in text
        # Backup creado.
        backups = list(paths.zellij_config.parent.glob("config.kdl.bak.*"))
        assert backups
