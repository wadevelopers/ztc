from __future__ import annotations

import subprocess
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static, Tree
from textual.widgets.option_list import Option
from textual.widgets.tree import TreeNode

from term_config_tui.models.layout import Layout, Pane, Tab
from term_config_tui.services import kdl_io, layout_ops, zellij_session
from term_config_tui.widgets.confirm import (
    ConfirmByNameModal,
    NewSessionModal,
    NewSessionResult,
    PaneEditModal,
    PickSessionModal,
    PostSaveLayoutModal,
    PromptModal,
)


class LayoutEditorScreen(Screen[None]):
    """Editor de un layout. Tabs, arbol de panes, preview KDL en vivo."""

    BINDINGS = [
        # Pane operations
        Binding("a", "add_pane", "Anadir pane"),
        Binding("s", "split_pane", "Partir"),
        Binding("d", "delete_pane", "Borrar pane"),
        Binding("e", "edit_pane", "Editar"),
        Binding("J", "move_down", "Bajar"),
        Binding("K", "move_up", "Subir"),
        Binding("greater_than_sign", "size_up", "+5%"),
        Binding("less_than_sign", "size_down", "-5%"),
        # Tab operations
        Binding("n", "new_tab", "Nueva tab"),
        Binding("D", "delete_tab", "Borrar tab"),
        Binding("r", "rename_tab", "Renombrar tab"),
        # Save / back
        Binding("ctrl+s", "save", "Guardar"),
        Binding("escape", "back", "Volver"),
    ]

    DEFAULT_CSS = """
    LayoutEditorScreen {
        layout: vertical;
    }
    #header-info {
        padding: 0 1;
        height: 1;
    }
    #editor-body {
        height: 60%;
    }
    #tabs-list {
        width: 28;
        border-right: solid $panel;
    }
    Tree {
        padding: 0 1;
    }
    #preview-wrap {
        height: 1fr;
        border-top: solid $panel;
    }
    #preview-title {
        padding: 0 1;
        color: $text-muted;
        height: 1;
    }
    #preview {
        padding: 0 2;
    }
    """

    def __init__(self, layout: Layout, layouts_dir: Path) -> None:
        super().__init__()
        self.layout_model = layout
        self.layouts_dir = layouts_dir
        self.dirty = False
        self._selected_tab_index = 0 if layout.tabs else -1
        self._selected_pane_id: int | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="header-info")
        with Horizontal(id="editor-body"):
            yield OptionList(id="tabs-list")
            yield Tree("(layout)", id="pane-tree")
        with Vertical(id="preview-wrap"):
            yield Static("Preview KDL", id="preview-title")
            with VerticalScroll():
                yield Static("", id="preview")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_header()
        self._rebuild_tabs()
        self._rebuild_tree()
        self._refresh_preview()

    # ---------- header / preview / tabs ----------

    def _refresh_header(self) -> None:
        dirty = " *" if self.dirty else ""
        self.query_one("#header-info", Static).update(
            f"[b]{self.layout_model.name}[/b]{dirty}    {self.layout_model.path}"
        )

    def _refresh_preview(self) -> None:
        preview = self.query_one("#preview", Static)
        preview.update(kdl_io.dump_layout(self.layout_model))

    def _rebuild_tabs(self) -> None:
        option_list = self.query_one("#tabs-list", OptionList)
        option_list.clear_options()
        for i, tab in enumerate(self.layout_model.tabs):
            label = tab.name or f"(tab #{i + 1})"
            option_list.add_option(Option(label, id=str(i)))
        if self.layout_model.tabs:
            self._selected_tab_index = max(
                0, min(self._selected_tab_index, len(self.layout_model.tabs) - 1)
            )
            option_list.highlighted = self._selected_tab_index
        else:
            self._selected_tab_index = -1

    @on(OptionList.OptionHighlighted, "#tabs-list")
    def _on_tab_highlight(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is None:
            return
        self._selected_tab_index = int(event.option.id)
        self._selected_pane_id = None
        self._rebuild_tree()

    # ---------- pane tree ----------

    def _current_tab(self) -> Tab | None:
        if 0 <= self._selected_tab_index < len(self.layout_model.tabs):
            return self.layout_model.tabs[self._selected_tab_index]
        return None

    def _rebuild_tree(self) -> None:
        tree = self.query_one("#pane-tree", Tree)
        tree.clear()
        tab = self._current_tab()
        if tab is None:
            tree.root.label = "(sin tabs)"
            return
        tree.root.label = f"tab: {tab.name or '(sin nombre)'}"
        tree.root.expand()
        for pane in tab.children:
            self._add_pane_node(tree.root, pane)
        self._restore_selection(tree)

    def _add_pane_node(self, parent: TreeNode[Pane], pane: Pane) -> TreeNode[Pane]:
        node = parent.add(self._pane_label(pane), data=pane, expand=True)
        for child in pane.children:
            self._add_pane_node(node, child)
        return node

    def _pane_label(self, pane: Pane) -> str:
        parts: list[str] = []
        if pane.is_container:
            parts.append(f"[ {pane.split_direction or 'container'} ]")
        else:
            parts.append("pane")
        if pane.size:
            parts.append(f"[{pane.size}]")
        if pane.name:
            parts.append(f'"{pane.name}"')
        if pane.command:
            parts.append(f"command={pane.command}")
        if pane.start_suspended:
            parts.append("suspended")
        if pane.focus:
            parts.append("focus")
        return "  ".join(parts)

    def _restore_selection(self, tree: Tree[Pane]) -> None:
        if self._selected_pane_id is None:
            return
        target_node = self._find_node(tree.root, self._selected_pane_id)
        if target_node is not None:
            tree.select_node(target_node)
            tree.scroll_to_node(target_node)

    def _find_node(
        self, node: TreeNode[Pane], pane_id: int
    ) -> TreeNode[Pane] | None:
        if node.data is not None and id(node.data) == pane_id:
            return node
        for child in node.children:
            result = self._find_node(child, pane_id)
            if result is not None:
                return result
        return None

    def _selected_pane(self) -> Pane | None:
        tree = self.query_one("#pane-tree", Tree)
        node = tree.cursor_node
        if node is None or node.data is None:
            return None
        return node.data

    # ---------- mutation helpers ----------

    def _mark_dirty(self) -> None:
        if not self.dirty:
            self.dirty = True
        self._refresh_header()
        self._refresh_preview()

    def _after_mutation(self, focus_pane: Pane | None) -> None:
        if focus_pane is not None:
            self._selected_pane_id = id(focus_pane)
        self._rebuild_tree()
        self._mark_dirty()

    # ---------- pane actions ----------

    def action_add_pane(self) -> None:
        if self._current_tab() is None:
            return
        target = self._selected_pane()
        if target is None:
            new_pane = Pane()
            self._current_tab().children.append(new_pane)  # type: ignore[union-attr]
        else:
            new_pane = layout_ops.add_sibling(self.layout_model, self._selected_tab_index, target)
            if new_pane is None:
                return
        self._after_mutation(new_pane)

    def action_split_pane(self) -> None:
        target = self._selected_pane()
        if target is None or self._current_tab() is None:
            return
        new_pane = layout_ops.split_pane(
            self.layout_model, self._selected_tab_index, target, direction="vertical"
        )
        self._after_mutation(new_pane)

    def action_delete_pane(self) -> None:
        target = self._selected_pane()
        if target is None or self._current_tab() is None:
            return
        if layout_ops.delete_pane(self.layout_model, self._selected_tab_index, target):
            self._selected_pane_id = None
            self._rebuild_tree()
            self._mark_dirty()

    def action_edit_pane(self) -> None:
        target = self._selected_pane()
        if target is None:
            return

        def after(replacement: Pane | None) -> None:
            if replacement is None:
                return
            if layout_ops.replace_pane(
                self.layout_model, self._selected_tab_index, target, replacement
            ):
                self._after_mutation(replacement)

        self.app.push_screen(PaneEditModal(target), after)

    def action_move_up(self) -> None:
        target = self._selected_pane()
        if target is None:
            return
        if layout_ops.move_pane(
            self.layout_model, self._selected_tab_index, target, delta=-1
        ):
            self._after_mutation(target)

    def action_move_down(self) -> None:
        target = self._selected_pane()
        if target is None:
            return
        if layout_ops.move_pane(
            self.layout_model, self._selected_tab_index, target, delta=1
        ):
            self._after_mutation(target)

    def action_size_up(self) -> None:
        target = self._selected_pane()
        if target is None:
            return
        if layout_ops.resize_pane(target, delta_pct=5):
            self._after_mutation(target)

    def action_size_down(self) -> None:
        target = self._selected_pane()
        if target is None:
            return
        if layout_ops.resize_pane(target, delta_pct=-5):
            self._after_mutation(target)

    # ---------- tab actions ----------

    def action_new_tab(self) -> None:
        def after(name: str | None) -> None:
            if not name:
                return
            tab = layout_ops.add_tab(self.layout_model, name)
            self._selected_tab_index = len(self.layout_model.tabs) - 1
            self._selected_pane_id = id(tab.children[0]) if tab.children else None
            self._rebuild_tabs()
            self._rebuild_tree()
            self._mark_dirty()

        self.app.push_screen(
            PromptModal(
                title="Nueva tab",
                placeholder="ej. dev",
                confirm_label="Crear",
            ),
            after,
        )

    def action_delete_tab(self) -> None:
        tab = self._current_tab()
        if tab is None:
            return

        def do_delete() -> None:
            if not layout_ops.delete_tab(self.layout_model, self._selected_tab_index):
                return
            if self._selected_tab_index >= len(self.layout_model.tabs):
                self._selected_tab_index = max(0, len(self.layout_model.tabs) - 1)
            self._selected_pane_id = None
            self._rebuild_tabs()
            self._rebuild_tree()
            self._mark_dirty()

        if tab.name:
            self.app.push_screen(
                ConfirmByNameModal(
                    title="Borrar tab",
                    message=(
                        f"Esto borrara la tab '{tab.name}' del layout "
                        "(no del disco hasta guardar)."
                    ),
                    expected=tab.name,
                    confirm_label="Borrar",
                ),
                lambda ok: do_delete() if ok else None,
            )
        else:
            self.app.push_screen(
                PromptModal(
                    title=f"Borrar tab #{self._selected_tab_index + 1}",
                    placeholder="escribe SI para confirmar",
                    confirm_label="Borrar",
                ),
                lambda result: do_delete() if result == "SI" else None,
            )

    def action_rename_tab(self) -> None:
        tab = self._current_tab()
        if tab is None:
            return

        def after(name: str | None) -> None:
            if name is None:
                return
            if layout_ops.rename_tab(self.layout_model, self._selected_tab_index, name):
                self._rebuild_tabs()
                self._rebuild_tree()
                self._mark_dirty()

        self.app.push_screen(
            PromptModal(
                title="Renombrar tab",
                initial=tab.name or "",
                placeholder="nombre de la tab",
                confirm_label="Renombrar",
                allow_empty=True,
            ),
            after,
        )

    # ---------- save / back ----------

    def action_save(self) -> None:
        try:
            backup = kdl_io.write_layout(self.layout_model)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Error al guardar: {exc}", severity="error", timeout=10)
            return
        self.dirty = False
        self._refresh_header()
        self.app.push_screen(
            PostSaveLayoutModal(
                layout_name=self.layout_model.name,
                backup_name=backup.name if backup else None,
            ),
            self._after_post_save,
        )

    def _after_post_save(self, choice: str | None) -> None:
        if choice in (None, "close"):
            return
        if choice == "new_session":
            self._flow_new_session()
        elif choice == "recreate":
            self._flow_recreate()
        elif choice == "sessions":
            self._flow_open_sessions()

    def _flow_new_session(self) -> None:
        if zellij_session.is_inside_zellij():
            self.app.notify(
                "Estas dentro de zellij; no se puede crear otra sesion desde aqui. "
                "Detach (Ctrl+O d) y vuelve a lanzar el TUI fuera de zellij.",
                severity="warning",
                timeout=10,
            )
            return

        def after(result: NewSessionResult | None) -> None:
            if result is None:
                return
            argv = zellij_session.new_session_argv(
                result.name, layout=self.layout_model.name
            )
            try:
                with self.app.suspend():
                    subprocess.run(argv, check=False)
            except Exception as exc:  # noqa: BLE001
                self.app.notify(f"Error al lanzar zellij: {exc}", severity="error")

        self.app.push_screen(
            NewSessionModal(title=f"Nueva sesion con layout '{self.layout_model.name}'"),
            after,
        )

    def _flow_recreate(self) -> None:
        if zellij_session.is_inside_zellij():
            self.app.notify(
                "Estas dentro de zellij; no se puede recrear sesiones desde aqui. "
                "Detach (Ctrl+O d) y vuelve a lanzar el TUI fuera de zellij.",
                severity="warning",
                timeout=10,
            )
            return

        sessions = zellij_session.list_sessions()
        running = [s for s in sessions if s.state == "running"]
        if not running:
            self.app.notify(
                "No hay sesiones vivas que recrear. Crea una nueva en su lugar.",
                severity="information",
            )
            return

        current = zellij_session.current_session_name()
        options = [
            (s.name, f"{'* ' if s.is_current else '  '}{s.name}    {s.raw_line or ''}")
            for s in running
        ]

        def after_pick(name: str | None) -> None:
            if name is None:
                return
            self._confirm_and_recreate(name)

        self.app.push_screen(
            PickSessionModal(
                title=f"Recrear con layout '{self.layout_model.name}'",
                options=options,
                current_session=current,
            ),
            after_pick,
        )

    def _confirm_and_recreate(self, name: str) -> None:
        def after_confirm(ok: bool) -> None:
            if not ok:
                return
            self._do_recreate(name)

        self.app.push_screen(
            ConfirmByNameModal(
                title="Recrear sesion",
                message=(
                    f"Esto cerrara la sesion '{name}' (todos los procesos dentro "
                    f"se cierran) y la creara de nuevo con el layout "
                    f"'{self.layout_model.name}'."
                ),
                expected=name,
                confirm_label="Recrear",
            ),
            after_confirm,
        )

    def _do_recreate(self, name: str) -> None:
        ok, out = zellij_session.kill_session(name)
        if not ok:
            self.app.notify(
                f"No se pudo cerrar '{name}': {out or 'sin output'}",
                severity="error",
                timeout=10,
            )
            return
        argv = zellij_session.new_session_argv(name, layout=self.layout_model.name)
        try:
            with self.app.suspend():
                subprocess.run(argv, check=False)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Error al recrear: {exc}", severity="error")

    def _flow_open_sessions(self) -> None:
        from term_config_tui.screens.session_manager import SessionManagerScreen

        self.app.pop_screen()  # cierra editor
        self.app.push_screen(
            SessionManagerScreen(layouts_dir=self.layouts_dir)
        )

    def action_back(self) -> None:
        if not self.dirty:
            self.app.pop_screen()
            return

        def after(ok: bool) -> None:
            if ok:
                self.app.pop_screen()

        self.app.push_screen(
            ConfirmByNameModal(
                title="Hay cambios sin guardar",
                message=(
                    "Si vuelves ahora, perderas los cambios. "
                    "Cancela y pulsa Ctrl+S para guardar."
                ),
                expected="descartar",
                confirm_label="Descartar cambios",
            ),
            after,
        )
