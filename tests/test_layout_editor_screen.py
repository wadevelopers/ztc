from __future__ import annotations

import shutil
from pathlib import Path

from textual.widgets import OptionList, Tree

from term_config_tui.app import TermConfigApp
from term_config_tui.models.config import Paths
from term_config_tui.screens.layout_editor import LayoutEditorScreen
from term_config_tui.screens.layout_list import LayoutListScreen
from term_config_tui.services import kdl_io
from term_config_tui.services.runtime_detect import TerminalDetection
from term_config_tui.services.terminals.alacritty import AlacrittyBackend
from term_config_tui.widgets.confirm import (
    ConfirmByNameModal,
    PaneEditModal,
)

FIX = Path(__file__).parent / "fixtures" / "zellij"


def _paths_with_layout(tmp_path: Path) -> Paths:
    layouts_dir = tmp_path / "layouts"
    layouts_dir.mkdir()
    shutil.copy2(FIX / "layout_simple.kdl", layouts_dir / "dev.kdl")
    return Paths(
        zellij_config=tmp_path / "config.kdl",
        zellij_layouts_dir=layouts_dir,
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


async def test_layout_list_shows_existing(tmp_path: Path) -> None:
    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter")  # navega a "Layouts Zellij"
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LayoutListScreen)
        option_list = screen.query_one("#layout-list", OptionList)
        ids = [
            option_list.get_option_at_index(i).id
            for i in range(option_list.option_count)
        ]
        assert ids == ["dev"]


async def test_layout_editor_opens_and_renders_preview(tmp_path: Path) -> None:
    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")  # menu -> layouts -> dev
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LayoutEditorScreen)

        tabs_list = screen.query_one("#tabs-list", OptionList)
        tab_ids = [tabs_list.get_option_at_index(i).id for i in range(tabs_list.option_count)]
        assert tab_ids == ["0", "1"]  # system, dev

        tree = screen.query_one("#pane-tree", Tree)
        assert tree.root.children  # tiene panes

        preview_text = kdl_io.dump_layout(screen.layout_model)
        assert "layout {" in preview_text
        assert 'tab name="system"' in preview_text


async def test_layout_editor_save_writes_file(tmp_path: Path) -> None:
    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LayoutEditorScreen)

        # Modificar el modelo en memoria para forzar dirty.
        screen.layout_model.tabs[0].children.append(
            screen.layout_model.tabs[0].children[0].__class__()
        )
        screen.dirty = True
        screen._rebuild_tree()
        screen.action_save()
        await pilot.pause()

        on_disk = kdl_io.load_layout(paths.zellij_layouts_dir / "dev.kdl")
        assert len(on_disk.tabs[0].children) == 2
        backups = list(paths.zellij_layouts_dir.glob("dev.kdl.bak.*"))
        assert backups


async def test_layout_editor_back_with_unsaved_prompts(tmp_path: Path) -> None:
    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LayoutEditorScreen)
        screen.dirty = True
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmByNameModal)


async def test_pane_edit_modal_returns_changes(tmp_path: Path) -> None:
    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LayoutEditorScreen)
        # Selecciona la primera tab "system" y su primer pane (btop).
        tree = screen.query_one("#pane-tree", Tree)
        first_pane_node = tree.root.children[0]
        tree.select_node(first_pane_node)
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, PaneEditModal)
        # Cancelar el modal: no cambia el modelo.
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, LayoutEditorScreen)
        assert app.screen.layout_model.tabs[0].children[0].command == "btop"


async def test_layout_editor_save_notifies_and_stays(tmp_path: Path) -> None:
    """Despues del split de sesiones a zsm, save solo guarda y notifica."""
    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LayoutEditorScreen)
        screen.action_save()
        await pilot.pause()
        # No abre modal: queda en el editor.
        assert isinstance(app.screen, LayoutEditorScreen)
        assert not screen.dirty


async def test_layout_list_new_creates_file(tmp_path: Path) -> None:
    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter")  # abrir layouts
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LayoutListScreen)
        # Llamar directamente al action y simular el callback (mas estable que pilot).
        screen.action_new()
        await pilot.pause()
        # Escribir el nombre y submit.
        for ch in "trabajo":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        # Tras crear deberia haber empujado el editor.
        assert isinstance(app.screen, LayoutEditorScreen)
        assert (paths.zellij_layouts_dir / "trabajo.kdl").exists()
