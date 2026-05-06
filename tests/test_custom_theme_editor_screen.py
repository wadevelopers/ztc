from __future__ import annotations

from pathlib import Path

from textual.widgets import OptionList

from term_config_tui.app import TermConfigApp
from term_config_tui.models.config import Paths
from term_config_tui.screens.custom_theme_editor import CustomThemeEditorScreen
from term_config_tui.screens.theme_editor import ThemePickerScreen
from term_config_tui.services import zellij_themes
from term_config_tui.services.runtime_detect import TerminalDetection
from term_config_tui.services.terminals.alacritty import AlacrittyBackend
from term_config_tui.widgets.confirm import (
    ConfirmByNameModal,
    PromptModal,
)


def _paths_with_user_themes(tmp_path: Path) -> Paths:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        '// header\n'
        'themes {\n'
        '    custom_dark {\n'
        '        fg "#cdd6f4"\n'
        '        bg "#585b70"\n'
        '    }\n'
        '}\n'
        'theme "custom_dark"\n',
        encoding="utf-8",
    )
    return Paths(
        zellij_config=cfg,
        zellij_layouts_dir=tmp_path / "layouts",
    )


def _make_app(tmp_path: Path, paths: Paths) -> TermConfigApp:
    return TermConfigApp(
        paths=paths,
        backend=AlacrittyBackend(),
        backend_path=tmp_path / "alacritty.toml",
        detection=TerminalDetection(
            kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
        ),
        zellij_installed=True,
    )


async def test_picker_clone_action_creates_user_theme(tmp_path: Path) -> None:
    paths = _paths_with_user_themes(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("enter")  # menu -> Tema Zellij
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThemePickerScreen)
        # Asegurar que el highlight esta en custom_dark (user, primero alfabeticamente entre user).
        screen.action_clone_theme()
        await pilot.pause()
        assert isinstance(app.screen, PromptModal)
        for ch in "custom_copy":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        names = {t.name for t in zellij_themes.list_user_themes(paths.zellij_config)}
        assert "custom_copy" in names
        assert "custom_dark" in names  # original preservado


async def test_picker_delete_user_theme(tmp_path: Path) -> None:
    paths = _paths_with_user_themes(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThemePickerScreen)
        screen.action_delete_theme()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmByNameModal)
        for ch in "custom_dark":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        names = {t.name for t in zellij_themes.list_user_themes(paths.zellij_config)}
        assert "custom_dark" not in names


async def test_picker_delete_blocks_builtin(tmp_path: Path) -> None:
    paths = _paths_with_user_themes(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThemePickerScreen)
        # Forzar highlight en un built-in seleccionado por id directamente
        option_list = screen.query_one("#theme-list", OptionList)
        for i in range(option_list.option_count):
            opt = option_list.get_option_at_index(i)
            if opt.id == "dracula":
                option_list.highlighted = i
                break
        await pilot.pause()
        screen.action_delete_theme()
        await pilot.pause()
        # No abre modal porque dracula no es user.
        assert not isinstance(app.screen, ConfirmByNameModal)


async def test_custom_theme_editor_save_writes_block(tmp_path: Path) -> None:
    paths = _paths_with_user_themes(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ThemePickerScreen)
        screen.action_edit_theme()  # custom_dark esta resaltado por defecto
        await pilot.pause()
        editor = app.screen
        assert isinstance(editor, CustomThemeEditorScreen)
        # Modificar el modelo en memoria y guardar.
        from term_config_tui.models.theme import ZellijColor

        editor.theme.colors[0] = ZellijColor("fg", "#deadbe")
        editor.dirty = True
        editor.action_save()
        await pilot.pause()
        themes = {t.name: t for t in zellij_themes.list_user_themes(paths.zellij_config)}
        assert themes["custom_dark"].colors[0].value == "#deadbe"
