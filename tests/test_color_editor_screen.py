from __future__ import annotations

import shutil
from pathlib import Path

from textual.widgets import OptionList

from term_config_tui.app import TermConfigApp
from term_config_tui.models.config import Paths
from term_config_tui.screens.color_editor import AlacrittyColorEditorScreen
from term_config_tui.services import alacritty, toml_io
from term_config_tui.widgets.confirm import EditColorModal, PromptModal

ALACRITTY_FIX = Path(__file__).parent / "fixtures" / "alacritty"


def _paths(tmp_path: Path, *, with_alacritty: bool = True) -> Paths:
    cfg = tmp_path / "alacritty.toml"
    if with_alacritty:
        shutil.copy2(ALACRITTY_FIX / "alacritty_min.toml", cfg)
    return Paths(
        zellij_config=tmp_path / "config.kdl",
        zellij_layouts_dir=tmp_path / "layouts",
        alacritty_config=cfg,
    )


async def test_color_editor_lists_known_slots(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    app = TermConfigApp(paths=paths)
    async with app.run_test() as pilot:
        # Menu -> Colores Alacritty (4to item).
        await pilot.press("down", "down", "down", "enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, AlacrittyColorEditorScreen)
        option_list = screen.query_one("#slot-list", OptionList)
        ids = {
            option_list.get_option_at_index(i).id
            for i in range(option_list.option_count)
        }
        # Debe haber un option por slot conocido.
        assert ids == {f"{g}.{n}" for g, n in alacritty.KNOWN_SLOTS}


async def test_color_editor_save_writes_changes(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    app = TermConfigApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "down", "down", "enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, AlacrittyColorEditorScreen)
        # Modificar via servicio para evitar fragilidad del modal.
        alacritty.write_slot(screen.doc, "primary", "background", "#abcdef")
        screen.dirty = True
        screen.action_save()
        await pilot.pause()

        on_disk = toml_io.load_toml(paths.alacritty_config)
        assert alacritty.read_slot(on_disk, "primary", "background") == "#abcdef"
        assert list(paths.alacritty_config.parent.glob("alacritty.toml.bak.*"))


async def test_color_editor_edit_modal_opens(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    app = TermConfigApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "down", "down", "enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, AlacrittyColorEditorScreen)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, EditColorModal)


async def test_color_editor_import_via_action(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    app = TermConfigApp(paths=paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "down", "down", "enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, AlacrittyColorEditorScreen)
        screen.action_import()
        await pilot.pause()
        assert isinstance(app.screen, PromptModal)
        for ch in str(ALACRITTY_FIX / "dracula.toml"):
            await pilot.press(ch if ch != "/" else "slash")
        await pilot.press("enter")
        await pilot.pause()

        # El doc en memoria debe tener los valores de dracula.
        assert alacritty.read_slot(screen.doc, "primary", "background") == "#282a36"
        assert screen.dirty is True
