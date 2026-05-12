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
    ConfirmActionModal,
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


async def test_layout_list_delete_uses_simple_confirm(tmp_path: Path) -> None:
    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LayoutListScreen)

        screen.action_delete()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmActionModal)
        await pilot.press("tab", "enter")
        await pilot.pause()

        assert not (paths.zellij_layouts_dir / "dev.kdl").exists()


async def test_layout_editor_delete_tab_deletes_without_confirm(tmp_path: Path) -> None:
    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LayoutEditorScreen)
        original_count = len(screen.layout_model.tabs)

        screen.action_delete_tab()
        await pilot.pause()

        assert isinstance(app.screen, LayoutEditorScreen)
        assert len(app.screen.layout_model.tabs) == original_count - 1
        assert app.screen.dirty is True


async def test_layout_editor_tab_footer_orders_rename_before_delete(
    tmp_path: Path,
) -> None:
    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LayoutEditorScreen)

        label = screen._tab_keys_label()
        assert label.index("New") < label.index("Rename") < label.index("Delete")


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


async def test_pane_edit_modal_validates_size(tmp_path: Path) -> None:
    """Size acepta porcentajes sin comillas."""
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

        size_input = modal.query_one("#size", Input)
        for bad in ('"60%"', "ab", "0.5", "0", "1", "101%"):
            size_input.value = bad
            modal._submit()
            await pilot.pause()
            assert isinstance(app.screen, PaneEditModal)

        size_input.value = "60%"
        modal._submit()
        await pilot.pause()

        assert isinstance(app.screen, LayoutEditorScreen)
        assert app.screen.layout_model.tabs[0].children[0].size == "60%"


async def test_container_pane_modal_exposes_only_structural_fields(
    tmp_path: Path,
) -> None:
    """Containers organizan panes; no exponen foco ni colores terminal."""
    from textual.widgets import Input

    from ztc.models.layout import Pane

    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    container = Pane(
        name="wrap",
        size="60%",
        focus=True,
        default_bg="#6272a4",
        default_fg="#f8f8f2",
        split_direction="vertical",
        children=[Pane(name="a"), Pane(name="b")],
    )
    async with app.run_test() as pilot:
        app.push_screen(PaneEditModal(container))
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, PaneEditModal)

        assert modal.query("#split")
        for selector in ("#focus", "#default_bg", "#default_fg", "#command"):
            assert not modal.query(selector)

        captured: list[Pane | None] = []

        def capture(result: Pane | None) -> None:
            captured.append(result)

        modal.dismiss = capture  # type: ignore[method-assign]
        modal.query_one("#name", Input).value = "wrap2"
        modal._submit()

        result = captured[0]
        assert result is not None
        assert result.name == "wrap2"
        assert result.size == "60%"
        assert result.split_direction == "vertical"
        assert result.focus is False
        assert result.default_bg is None
        assert result.default_fg is None
        assert len(result.children) == 2


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


async def test_tree_cursor_skips_property_rows_at_end_of_tree(tmp_path: Path) -> None:
    """Edge case: si la ultima fila visible del arbol es una property
    row (atributo de un leaf expandido), el cursor no debe quedarse
    parado ahi. Debe revertir a la ultima posicion data-bearing."""
    from ztc.models.layout import Pane

    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        editor = app.screen
        assert isinstance(editor, LayoutEditorScreen)

        # Tab con un solo pane que tiene atributos (genera filas hijas).
        editor.layout_model.tabs[0].children = [
            Pane(name="solo", command="vim", default_bg="#6272a4"),
        ]
        editor._rebuild_tree()
        await pilot.pause()

        tree = editor.query_one("#pane-tree", Tree)
        leaf_node = tree.root.children[0]
        # Asegurar que esta expandido para que las property rows sean visibles.
        leaf_node.expand()
        await pilot.pause()
        # Selecciono el pane y trato de bajar mas alla del ultimo nodo:
        # como solo hay property rows debajo, el cursor debe quedarse
        # en el pane (no en una property row).
        tree.select_node(leaf_node)
        starting_line = tree.cursor_line
        # Simular varios `down` consecutivos: el cursor no debe terminar
        # nunca en un nodo data=None.
        for _ in range(5):
            tree.action_cursor_down()
        await pilot.pause()
        assert tree.cursor_node is not None
        assert tree.cursor_node.data is not None  # nunca property row
        # Y debe seguir en el unico pane disponible.
        assert tree.cursor_line == starting_line


async def test_tree_cursor_reaches_root_via_arrow_keys(tmp_path: Path) -> None:
    """La raiz `tab: xxx` es navegable con flechas. Aunque tenga
    `data is None`, no es una property row (no tiene parent con data),
    asi que el skip de property rows la deja en paz."""
    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        editor = app.screen
        assert isinstance(editor, LayoutEditorScreen)

        tree = editor.query_one("#pane-tree", Tree)
        # Posicionar cursor en el primer pane.
        first_pane = tree.root.children[0]
        tree.select_node(first_pane)
        tree.move_cursor(first_pane)
        await pilot.pause()
        assert tree.cursor_node is first_pane

        # Up desde el primer pane debe llegar a la raiz.
        tree.action_cursor_up()
        await pilot.pause()
        assert tree.cursor_node is tree.root


async def test_tree_property_row_redirects_to_parent_on_direct_cursor(tmp_path: Path) -> None:
    """Si el cursor cae en una property row sin pasar por
    `action_cursor_*` (tipico del click del mouse, que setea cursor
    directo via `move_cursor`), debe redirigir automaticamente al
    pane padre. El handler `on_tree_node_highlighted` cubre este
    caso como fallback al skip de teclado."""
    from ztc.models.layout import Pane

    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test() as pilot:
        await pilot.press("down", "enter", "enter")
        await pilot.pause()
        editor = app.screen
        assert isinstance(editor, LayoutEditorScreen)
        editor.layout_model.tabs[0].children = [
            Pane(name="solo", command="vim", default_bg="#6272a4"),
        ]
        editor._rebuild_tree()
        await pilot.pause()
        tree = editor.query_one("#pane-tree", Tree)
        leaf_node = tree.root.children[0]
        leaf_node.expand()
        await pilot.pause()

        # Simular click del mouse: mover cursor directo a una property
        # row (children del leaf son las property rows, todas con data=None).
        property_node = leaf_node.children[0]
        assert property_node.data is None  # confirma que es property row

        tree.move_cursor(property_node)
        await pilot.pause()

        # El handler debe redirigir al pane padre (data-bearing).
        assert tree.cursor_node is leaf_node
        assert tree.cursor_node.data is not None


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

        # Static.content devuelve el markup string actual. Formato bg
        # color (espejando _inline_swatch del arbol para consistencia):
        # `[on #color]  [/]` cuando hay color valido, `"  "` cuando no.
        bg_input.value = "#6272a4"
        await pilot.pause()
        assert "[on #6272a4]  [/]" in str(bg_preview.content)

        # Valido en rgb: el helper convierte a hex para Rich.
        bg_input.value = "rgb:6c/72/a4"
        await pilot.pause()
        assert "[on #6c72a4]  [/]" in str(bg_preview.content)

        # Invalido: preview limpio (solo espacios, sin markup `on `).
        bg_input.value = "garbage"
        await pilot.pause()
        assert "on " not in str(bg_preview.content)


async def test_pane_edit_modal_fields_stay_inside_dialog(
    tmp_path: Path,
) -> None:
    """Los controles de cada fila deben quedar dentro del ancho visible."""

    paths = _paths_with_layout(tmp_path)
    app = _make_app(tmp_path, paths)
    async with app.run_test(size=(80, 24)) as pilot:
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

        dialog = modal.query_one("#dialog")
        for selector in (
            "#name",
            "#size",
            "#focus",
            "#default_bg",
            "#default_bg-preview",
            "#default_fg",
            "#default_fg-preview",
            "#command",
            "#args",
            "#cwd",
            "#start_suspended",
            "#borderless",
        ):
            widget = modal.query_one(selector)
            assert widget.region.right <= dialog.region.right - 1

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, LayoutEditorScreen)

        app.push_screen(PaneEditModal(editor.layout_model.tabs[1].children[0]))
        await pilot.pause()
        container_modal = app.screen
        assert isinstance(container_modal, PaneEditModal)
        container_dialog = container_modal.query_one("#dialog")
        for selector in (
            "#name",
            "#size",
            "#split",
        ):
            widget = container_modal.query_one(selector)
            assert widget.region.right <= container_dialog.region.right - 1
        for selector in (
            "#focus",
            "#default_bg",
            "#default_bg-preview",
            "#default_fg",
            "#default_fg-preview",
            "#command",
            "#args",
            "#cwd",
            "#start_suspended",
            "#borderless",
        ):
            assert not container_modal.query(selector)
