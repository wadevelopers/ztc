from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static, Tree
from textual.widgets.option_list import Option
from textual.widgets.tree import TreeNode

from ztc.models.layout import Layout, Pane, Tab
from ztc.zellij import layout_io, layout_ops
from ztc.widgets.confirm import (
    ConfirmByNameModal,
    PaneEditModal,
    PromptModal,
)


class LayoutEditorScreen(Screen[None]):
    """Editor de un layout. Tabs, arbol de panes, preview KDL en vivo."""

    BINDINGS = [
        # Pane operations
        Binding("a", "add_pane", "Add pane"),
        Binding("s", "split_pane", "Split"),
        Binding("d", "delete_pane", "Delete pane"),
        Binding("e", "edit_pane", "Edit"),
        Binding("J", "move_down", "Move down"),
        Binding("K", "move_up", "Move up"),
        Binding("greater_than_sign", "size_up", "+5%"),
        Binding("less_than_sign", "size_down", "-5%"),
        # Tab operations
        Binding("n", "new_tab", "New tab"),
        Binding("D", "delete_tab", "Delete tab"),
        Binding("r", "rename_tab", "Rename tab"),
        # Save / back
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "back", "Back"),
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
        preview.update(layout_io.dump_layout(self.layout_model))

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
            tree.root.label = "(no tabs)"
            return
        tree.root.label = f"tab: {tab.name or '(unnamed)'}"
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
                title="New tab",
                placeholder="e.g. dev",
                confirm_label="Create",
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
                    title="Delete tab",
                    message=(
                        f"This will remove tab '{tab.name}' from the layout "
                        "(not from disk until save)."
                    ),
                    expected=tab.name,
                    confirm_label="Delete",
                ),
                lambda ok: do_delete() if ok else None,
            )
        else:
            self.app.push_screen(
                PromptModal(
                    title=f"Delete tab #{self._selected_tab_index + 1}",
                    placeholder="type YES to confirm",
                    confirm_label="Delete",
                ),
                lambda result: do_delete() if result == "YES" else None,
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
                title="Rename tab",
                initial=tab.name or "",
                placeholder="tab name",
                confirm_label="Rename",
                allow_empty=True,
            ),
            after,
        )

    # ---------- save / back ----------

    def action_save(self) -> None:
        try:
            backup = layout_io.write_layout(self.layout_model)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Save error: {exc}", severity="error", timeout=10)
            return
        self.dirty = False
        self._refresh_header()
        msg = f"Layout '{self.layout_model.name}' saved."
        if backup is not None:
            msg += f"  (backup: {backup.name})"
        msg += "  To launch it: use zsm."
        self.app.notify(msg, severity="information", timeout=8)

    def action_back(self) -> None:
        if not self.dirty:
            self.app.pop_screen()
            return

        def after(ok: bool) -> None:
            if ok:
                self.app.pop_screen()

        self.app.push_screen(
            ConfirmByNameModal(
                title="Unsaved changes",
                message=(
                    "If you go back now, you'll lose your changes. "
                    "Cancel and press Ctrl+S to save."
                ),
                expected="discard",
                confirm_label="Discard changes",
            ),
            after,
        )
