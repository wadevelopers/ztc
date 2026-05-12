from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from ztc.models.layout import Layout
from ztc.widgets.confirm import ConfirmActionModal, PromptModal
from ztc.widgets.header import StaticHeader
from ztc.zellij import config_ops, layout_io, layout_ops


class LayoutListScreen(Screen[None]):
    """Lista de layouts. Permite abrir, crear o borrar layouts."""

    BINDINGS = [
        Binding("enter", "open", "Open"),
        Binding("n", "new", "New"),
        Binding("d", "delete", "Delete"),
        Binding("r", "refresh", "Refresh"),
        Binding("escape", "app.pop_screen", "Back"),
        # `q` y `ctrl+q` neutralizados: solo `Esc` sale del listado.
        Binding("q", "noop", show=False),
        Binding("ctrl+q", "noop", show=False),
    ]

    def action_noop(self) -> None:
        pass

    DEFAULT_CSS = """
    LayoutListScreen {
        layout: vertical;
    }
    #status {
        padding: 0 1;
        height: 1;
        color: $text-muted;
    }
    #body {
        height: 1fr;
    }
    OptionList {
        width: 40;
        border-right: solid $panel;
    }
    #detail {
        padding: 1 2;
        height: 1fr;
    }
    #detail-name {
        text-style: bold;
        color: $accent;
    }
    """

    def __init__(self, layouts_dir: Path) -> None:
        super().__init__()
        self.layouts_dir = layouts_dir
        self._layouts: list[Layout] = []

    def compose(self) -> ComposeResult:
        yield StaticHeader()
        yield Static("", id="status")
        with Horizontal(id="body"):
            yield OptionList(id="layout-list")
            with Vertical(id="detail"):
                yield Static("Select a layout.", id="detail-name")
                yield Static("", id="detail-meta")
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh()

    def on_screen_resume(self) -> None:
        self.action_refresh()

    def action_refresh(self) -> None:
        self.layouts_dir.mkdir(parents=True, exist_ok=True)
        self._layouts = config_ops.list_layouts(self.layouts_dir)
        option_list = self.query_one("#layout-list", OptionList)
        option_list.clear_options()
        for layout in self._layouts:
            option_list.add_option(Option(self._format(layout), id=layout.name))
        self.query_one("#status", Static).update(
            f"{len(self._layouts)} layout(s) in {self.layouts_dir}"
        )
        if self._layouts:
            option_list.highlighted = 0
            self._show_detail(self._layouts[0])
        else:
            self._show_detail(None)

    def _format(self, layout: Layout) -> str:
        tabs = len(layout.tabs)
        marker = " (+raw)" if layout.raw_unknown_nodes else ""
        return f"{layout.name:<24}  {tabs} tab(s){marker}"

    def _show_detail(self, layout: Layout | None) -> None:
        name = self.query_one("#detail-name", Static)
        meta = self.query_one("#detail-meta", Static)
        if layout is None:
            name.update("No layouts.")
            meta.update("Press [b]n[/b] to create the first one.")
            return
        name.update(layout.name)
        tab_names = ", ".join((t.name or "(unnamed)") for t in layout.tabs)
        warn = ""
        if layout.raw_unknown_nodes:
            warn = (
                "\n\nThis layout contains nodes the editor does not understand "
                "(e.g. default_tab_template). They are preserved on save but "
                "may lose exact formatting. `/-` comments are discarded."
            )
        meta.update(f"Path: {layout.path}\nTabs: {tab_names}{warn}")

    @on(OptionList.OptionHighlighted, "#layout-list")
    def _on_highlight(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is None:
            return
        layout = next((layout for layout in self._layouts if layout.name == event.option.id), None)
        if layout is not None:
            self._show_detail(layout)

    @on(OptionList.OptionSelected, "#layout-list")
    def _on_select(self, event: OptionList.OptionSelected) -> None:
        self.action_open()

    def _highlighted(self) -> Layout | None:
        option_list = self.query_one("#layout-list", OptionList)
        if option_list.highlighted is None:
            return None
        opt = option_list.get_option_at_index(option_list.highlighted)
        return next((layout for layout in self._layouts if layout.name == opt.id), None)

    def action_open(self) -> None:
        layout = self._highlighted()
        if layout is None:
            return
        from ztc.screens.layout_editor import LayoutEditorScreen

        self.app.push_screen(LayoutEditorScreen(layout=layout, layouts_dir=self.layouts_dir))

    def action_new(self) -> None:
        def after(name: str | None) -> None:
            if not name:
                return
            if not layout_ops.is_valid_layout_name(name):
                self.app.notify(
                    f"Invalid name: {name!r}. Use letters, numbers, '-' and '_'.",
                    severity="error",
                )
                return
            target = self.layouts_dir / f"{name}.kdl"
            if target.exists():
                self.app.notify(
                    f"{target.name} already exists. "
                    "Use a different name or delete the existing one.",
                    severity="error",
                )
                return
            layout = layout_ops.new_blank_layout(self.layouts_dir, name)
            layout_io.write_layout(layout, backup=False)
            self.action_refresh()
            from ztc.screens.layout_editor import LayoutEditorScreen

            self.app.push_screen(
                LayoutEditorScreen(layout=layout, layouts_dir=self.layouts_dir)
            )

        self.app.push_screen(
            PromptModal(
                title="New layout",
                placeholder="e.g. work",
                confirm_label="Create",
            ),
            after,
        )

    def action_delete(self) -> None:
        layout = self._highlighted()
        if layout is None:
            return

        def after(ok: bool) -> None:
            if not ok:
                self.app.notify("Cancelled.", severity="information")
                return
            try:
                backup = layout_io.delete_layout(layout.path)
            except Exception as exc:  # noqa: BLE001
                self.app.notify(f"Delete error: {exc}", severity="error")
                return
            msg = f"Layout '{layout.name}' deleted"
            if backup is not None:
                msg += f" (backup: {backup.name})"
            self.app.notify(msg, severity="information")
            self.action_refresh()

        self.app.push_screen(
            ConfirmActionModal(
                title="Delete layout",
                message=f"This will delete the file {layout.path}.",
                confirm_label="Yes, delete",
            ),
            after,
        )
