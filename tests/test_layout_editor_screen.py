from __future__ import annotations

import shutil
from pathlib import Path

from textual.widgets import OptionList, Tree

from ztc.app import TermConfigApp
from ztc.models.config import Paths
from ztc.screens.layout_editor import LayoutEditorScreen
from ztc.screens.layout_list import LayoutListScreen
from ztc.services.runtime_detect import TerminalDetection
from ztc.services.terminals.alacritty import AlacrittyBackend
from ztc.widgets.confirm import (
    PaneEditModal,
    UnsavedChangesModal,
)
from ztc.zellij import layout_io as kdl_io

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
        assert isinstance(app.screen, UnsavedChangesModal)


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


# ---------- PaneEditModal: validacion de default_bg / default_fg ----------


async def test_pane_edit_modal_accepts_valid_default_bg_fg(tmp_path: Path) -> None:
    """Hex valido en bg y fg pasa la validacion y se aplica al modelo."""
    from textual.widgets import Input

    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")  # menu -> layouts -> dev
        await pilot.pause()
        editor = app.screen
        assert isinstance(editor, LayoutEditorScreen)
        # Mismo patron que test_pane_edit_modal_returns_changes: seleccionar
        # el primer pane via tree y abrir el modal.
        tree = editor.query_one("#pane-tree", Tree)
        first_pane_node = tree.root.children[0]
        tree.select_node(first_pane_node)
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, PaneEditModal)

        modal.query_one("#default_bg", Input).value = "#6272a4"
        modal.query_one("#default_fg", Input).value = "rgb:f8/f8/f2"
        modal._submit()
        await pilot.pause()

        # Modal debe haber cerrado y el pane del modelo tiene los colores.
        assert isinstance(app.screen, LayoutEditorScreen)
        edited_pane = app.screen.layout_model.tabs[0].children[0]
        assert edited_pane.default_bg == "#6272a4"
        assert edited_pane.default_fg == "rgb:f8/f8/f2"


async def test_pane_edit_modal_rejects_invalid_default_bg(tmp_path: Path) -> None:
    """Hex invalido bloquea el dismiss y el modal sigue abierto."""
    from textual.widgets import Input

    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        editor = app.screen
        assert isinstance(editor, LayoutEditorScreen)
        tree = editor.query_one("#pane-tree", Tree)
        first_pane_node = tree.root.children[0]
        tree.select_node(first_pane_node)
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, PaneEditModal)

        modal.query_one("#default_bg", Input).value = "not-a-color"
        modal._submit()
        await pilot.pause()

        # Modal SIGUE abierto (no dismiss en flujo de error).
        assert isinstance(app.screen, PaneEditModal)


# ---------- Stage 2: tree expand-to-attributes + pane label coloreado ----------


async def test_tree_leaf_with_attributes_expands_to_child_rows(tmp_path: Path) -> None:
    """Un leaf con atributos no-default genera filas hijas en el arbol
    (una por atributo). Verificamos que esten presentes con el nombre
    esperado."""
    from ztc.models.layout import Pane

    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        editor = app.screen
        assert isinstance(editor, LayoutEditorScreen)

        # Reemplazo el primer pane del modelo con uno repleto de atributos.
        editor.layout_model.tabs[0].children[0] = Pane(
            name="rich",
            command="vim",
            cwd="/tmp",
            start_suspended=True,
            default_bg="#6272a4",
            default_fg="#f8f8f2",
        )
        editor._rebuild_tree()
        await pilot.pause()

        tree = editor.query_one("#pane-tree", Tree)
        leaf_node = tree.root.children[0]
        # Las filas hijas son TreeNodes; verificamos que estan los
        # atributos no-default del pane que pusimos.
        child_labels = [str(child.label) for child in leaf_node.children]
        joined = " | ".join(child_labels)
        assert "command:" in joined
        assert "vim" in joined
        assert "cwd:" in joined
        assert "/tmp" in joined
        assert "start_suspended:" in joined
        assert "default_bg:" in joined
        assert "#6272a4" in joined
        assert "default_fg:" in joined
        assert "#f8f8f2" in joined


async def test_tree_empty_leaf_uses_add_leaf_no_expand(tmp_path: Path) -> None:
    """Un leaf sin atributos no-default no debe tener triangulo de expand.
    Implementado via `add_leaf` que setea `allow_expand=False`."""
    from ztc.models.layout import Pane

    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        editor = app.screen
        assert isinstance(editor, LayoutEditorScreen)

        # Pane vacio (sin atributos no-default ni nombre).
        editor.layout_model.tabs[0].children[0] = Pane()
        editor._rebuild_tree()
        await pilot.pause()

        tree = editor.query_one("#pane-tree", Tree)
        leaf_node = tree.root.children[0]
        assert leaf_node.allow_expand is False
        assert len(leaf_node.children) == 0


async def test_tree_leaf_label_uses_accent_markup(tmp_path: Path) -> None:
    """El label de un leaf debe envolver `pane` y el name con el hex
    resuelto de `$accent` para destacarse de containers + atributos."""
    from ztc.models.layout import Pane

    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        editor = app.screen
        assert isinstance(editor, LayoutEditorScreen)

        editor.layout_model.tabs[0].children[0] = Pane(name="hello")
        editor._rebuild_tree()
        await pilot.pause()

        # `_pane_label` produce el string que se asigna al label.
        label_text = editor._pane_label(editor.layout_model.tabs[0].children[0])
        # El accent fue resuelto en on_mount; debe estar presente en el
        # markup (sea hex como `#xxxxxx` o el fallback `cyan`).
        assert editor._accent_hex in label_text
        assert "pane" in label_text
        assert "hello" in label_text


# ---------- Stage 2: live color preview en el modal ----------


async def test_pane_edit_modal_color_preview_updates_on_input(tmp_path: Path) -> None:
    """Tipear un color valido en el Input actualiza el preview con
    el bg correspondiente. Tipear algo invalido lo limpia."""
    from textual.widgets import Input, Static

    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        editor = app.screen
        assert isinstance(editor, LayoutEditorScreen)
        tree = editor.query_one("#pane-tree", Tree)
        tree.select_node(tree.root.children[0])
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, PaneEditModal)

        bg_input = modal.query_one("#default_bg", Input)
        bg_preview = modal.query_one("#default_bg-preview", Static)

        # Static.content devuelve el markup string actual.
        # Valido en hex: el preview tiene markup con bg color.
        bg_input.value = "#6272a4"
        await pilot.pause()
        assert "#6272a4" in str(bg_preview.content)

        # Valido en rgb: el helper convierte a hex para Rich.
        bg_input.value = "rgb:6c/72/a4"
        await pilot.pause()
        assert "#6c72a4" in str(bg_preview.content)

        # Invalido: preview limpio (sin markup `on `).
        bg_input.value = "garbage"
        await pilot.pause()
        assert "on " not in str(bg_preview.content)
