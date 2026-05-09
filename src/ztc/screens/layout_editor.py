from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import OptionList, Static, Tree
from textual.widgets.option_list import Option
from textual.widgets.tree import TreeNode

from ztc.models.layout import Layout, Pane, Tab
from ztc.widgets.confirm import (
    ConfirmByNameModal,
    KdlPreviewModal,
    PaneEditModal,
    PromptModal,
)
from ztc.widgets.header import StaticHeader
from ztc.zellij import layout_io, layout_ops


class _LayoutTabsList(OptionList):
    """OptionList con bindings explicitos: replica los defaults de
    Textual con descriptions (sino aparecen sin label en el Command
    Palette al sobreescribir los heredados)."""

    BINDINGS = [
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("home", "first", "First", show=False),
        Binding("end", "last", "Last", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("enter", "select", "Select", show=False),
    ]


class _PaneTree(Tree):
    """Tree con bindings explicitos: navegacion vertical + expand/collapse,
    todos con description para que aparezcan con label en el Command
    Palette."""

    BINDINGS = [
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("space", "toggle_node", "Toggle", show=False),
        Binding("enter", "select_cursor", "Select", show=False),
    ]


class LayoutEditorScreen(Screen[None]):
    """Editor de un layout. Tabs, arbol de panes, preview KDL en vivo."""

    BINDINGS = [
        # Todas las hotkeys con show=False: no usamos Footer estandar de
        # Textual; las hotkeys se muestran en filas Static custom
        # (Tabs / Panes / Move / File) que reemplazan al Footer.
        # Pane operations
        Binding("a", "add_pane", "Add", show=False),
        Binding("S", "split_pane", "Split", show=False),
        Binding("d", "delete_pane", "Delete", show=False),
        Binding("e", "edit_pane", "Edit", show=False),
        # Move (J/K contextual: opera sobre tabs o panes segun foco)
        Binding("J", "move_down", "Down", show=False),
        Binding("K", "move_up", "Up", show=False),
        # Tab operations
        Binding("n", "new_tab", "New tab", show=False),
        Binding("D", "delete_tab", "Del tab", show=False),
        Binding("R", "rename_tab", "Rename tab", show=False),
        # File operations
        Binding("p", "preview", "Preview KDL", show=False),
        Binding("r", "reload", "Reload", show=False),
        Binding("s", "save", "Save", show=False),
        Binding("escape", "back", "Back", show=False),
        Binding("q", "noop", show=False),
        Binding("ctrl+q", "noop", show=False),
    ]

    def action_noop(self) -> None:
        pass

    DEFAULT_CSS = """
    LayoutEditorScreen {
        layout: vertical;
    }
    #header-info {
        padding: 0 1;
        height: 1;
    }
    #editor-body {
        height: 1fr;
    }
    #tabs-list {
        width: 28;
        margin-right: 1;
    }
    Tree {
        padding: 0 1;
        border-left: solid $panel;
    }
    .keys-row {
        height: 1;
        padding: 0 1;
        background: $panel;
        color: $text-muted;
    }
    /* Fila con left/right alineados (Move). */
    .keys-row-split {
        height: 1;
        background: $panel;
        color: $text-muted;
    }
    .keys-row-split > .keys-left {
        width: 1fr;
        padding: 0 1;
    }
    .keys-row-split > .keys-right {
        width: auto;
        padding: 0 1;
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
        yield StaticHeader()
        yield Static("", id="header-info")
        with Horizontal(id="editor-body"):
            yield _LayoutTabsList(id="tabs-list")
            yield _PaneTree("(layout)", id="pane-tree")
        # Filas en orden escalonado de menor a mayor cantidad de chips:
        # Move (2), File (3), Tabs (3), Panes (4). Las columnas se alinean
        # verticalmente con padding por ancho de label.
        with Horizontal(id="move-keys", classes="keys-row-split"):
            yield Static(self._move_keys_label(), classes="keys-left")
            yield Static(self._back_keys_label(), classes="keys-right")
        with Horizontal(id="file-keys", classes="keys-row-split"):
            yield Static(self._file_keys_label(), classes="keys-left")
            yield Static(self._tab_focus_label(), classes="keys-right")
        with Horizontal(id="tab-keys", classes="keys-row-split"):
            yield Static(self._tab_keys_label(), classes="keys-left")
            yield Static(self._palette_keys_label(), classes="keys-right")
        yield Static(self._pane_keys_label(), id="pane-keys", classes="keys-row")

    @staticmethod
    def _key_chip(key: str, label: str, *, width: int | None = None) -> str:
        # Mismo estilo que el Footer de Textual: tecla en `$footer-key-foreground`
        # (= $accent en el tema activo) + bold; descripcion en color normal.
        # `width` opcional: padea el label con espacios a la derecha para
        # alinear columnas verticalmente entre filas distintas.
        if width is not None:
            label = label.ljust(width)
        return f"[$footer-key-foreground b]{key}[/] {label}"

    # Anchos por columna (label, sin la key + espacio):
    # Col 1: 6 = len("Reload"). Col 2: 6 = len("Delete"). Col 3: 7 = len("Preview").
    # Col 4 (solo en Panes "Edit") no se padea — es el ultimo chip de su fila.

    def _tab_keys_label(self) -> str:
        keys = [
            self._key_chip("n", "New", width=6),
            self._key_chip("D", "Delete", width=6),
            self._key_chip("R", "Rename", width=7),
        ]
        return "Tabs:  " + "  ".join(keys)

    def _pane_keys_label(self) -> str:
        keys = [
            self._key_chip("a", "Add", width=6),
            self._key_chip("S", "Split", width=6),
            self._key_chip("d", "Delete", width=7),
            self._key_chip("e", "Edit"),
        ]
        return "Panes: " + "  ".join(keys)

    def _move_keys_label(self) -> str:
        keys = [
            self._key_chip("J", "Down", width=6),
            self._key_chip("K", "Up", width=6),
        ]
        return "Move:  " + "  ".join(keys)

    def _back_keys_label(self) -> str:
        # Doble espacio entre `Esc` y `Back` para que la `E` quede
        # alineada verticalmente con la `P` de `P Palette` en la fila
        # de abajo (Esc Back = 8 chars, P Palette = 9; con 2 espacios
        # ambos miden 9).
        return "[$footer-key-foreground b]Esc[/]  Back"

    def _file_keys_label(self) -> str:
        keys = [
            self._key_chip("r", "Reload", width=6),
            self._key_chip("s", "Save", width=6),
            self._key_chip("p", "Preview", width=7),
        ]
        return "File:  " + "  ".join(keys)

    def _palette_keys_label(self) -> str:
        # `P` lo registra el App globalmente (action_command_palette).
        return self._key_chip("P", "Palette")

    def _tab_focus_label(self) -> str:
        # `Tab` y `Shift+Tab` son bindings default del Screen de Textual
        # para mover el foco entre widgets (focus_next / focus_previous).
        return self._key_chip("Tab", "Focus")

    def on_mount(self) -> None:
        self._refresh_header()
        self._rebuild_tabs()
        self._rebuild_tree()

    # ---------- header / preview / tabs ----------

    def _refresh_header(self) -> None:
        dirty = " *" if self.dirty else ""
        self.query_one("#header-info", Static).update(
            f"[b]{self.layout_model.name}[/b]{dirty}    {self.layout_model.path}"
        )

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
            # `select_node` marca seleccionado pero no mueve el cursor visual.
            # `move_cursor` mueve el highlight + scrollea — sin esto el cursor
            # se queda en la raiz tras cualquier _rebuild_tree.
            tree.move_cursor(target_node)
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
        # Capturamos sibling cercano antes de delete para mantener el cursor
        # en una posicion razonable (no al root).
        found = layout_ops.find_pane_parent(
            self.layout_model, self._selected_tab_index, target
        )
        next_focus: Pane | None = None
        if found is not None:
            siblings, idx = found
            # El sibling mas cercano: el siguiente, sino el anterior, sino None.
            if idx + 1 < len(siblings):
                next_focus = siblings[idx + 1]
            elif idx > 0:
                next_focus = siblings[idx - 1]
        if layout_ops.delete_pane(self.layout_model, self._selected_tab_index, target):
            self._selected_pane_id = id(next_focus) if next_focus is not None else None
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
        self._move(-1)

    def action_move_down(self) -> None:
        self._move(+1)

    def _move(self, delta: int) -> None:
        """Mover el item con foco actual: si el foco esta en la lista de
        tabs, mueve el tab; si esta en el arbol de panes (default),
        mueve el pane. Mismo binding J/K para ambos contextos."""
        if isinstance(self.focused, _LayoutTabsList):
            new_idx = layout_ops.move_tab(
                self.layout_model, self._selected_tab_index, delta=delta
            )
            if new_idx is not None:
                self._selected_tab_index = new_idx
                self._rebuild_tabs()
                self._rebuild_tree()
                self._mark_dirty()
            return
        # Default: mover pane.
        target = self._selected_pane()
        if target is None:
            return
        if layout_ops.move_pane(
            self.layout_model, self._selected_tab_index, target, delta=delta
        ):
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

    # ---------- preview ----------

    def action_preview(self) -> None:
        """Abre un modal con el KDL serializado actual del layout en
        memoria (refleja los cambios pending, no solo lo que esta en
        disco)."""
        text = layout_io.dump_layout(self.layout_model)
        title = f"KDL preview — {self.layout_model.name}"
        if self.dirty:
            title += " *"
        self.app.push_screen(KdlPreviewModal(title=title, content=text))

    # ---------- save / reload / back ----------

    def action_reload(self) -> None:
        """Re-lee el layout del disco descartando cambios pending. Mismo
        patron que ColorEditor / TerminalSettings (sin confirm — el
        usuario aprieta `r` con intencion de descartar)."""
        try:
            fresh = layout_io.load_layout(self.layout_model.path)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Reload error: {exc}", severity="error", timeout=8)
            return
        self.layout_model = fresh
        self._selected_tab_index = 0 if fresh.tabs else -1
        self._selected_pane_id = None
        self.dirty = False
        self._refresh_header()
        self._rebuild_tabs()
        self._rebuild_tree()
        self.app.notify("Reloaded from disk.", severity="information")

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
        from ztc.widgets.confirm import UnsavedChangesModal

        def after(choice: str | None) -> None:
            if choice == "discard":
                self.app.pop_screen()
                return
            if choice == "save":
                self.action_save()
                if not self.dirty:
                    self.app.pop_screen()
                return

        self.app.push_screen(UnsavedChangesModal(), after)
