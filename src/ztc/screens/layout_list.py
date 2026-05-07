from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from ztc.models.layout import Layout
from ztc.services import kdl_io, layout_ops, zellij_config
from ztc.widgets.confirm import ConfirmByNameModal, PromptModal


class LayoutListScreen(Screen[None]):
    """Lista de layouts. Permite abrir, crear o borrar layouts."""

    BINDINGS = [
        Binding("enter", "open", "Abrir"),
        Binding("n", "new", "Nuevo"),
        Binding("d", "delete", "Borrar"),
        Binding("r", "refresh", "Refrescar"),
        Binding("escape", "app.pop_screen", "Volver"),
        Binding("q", "app.pop_screen", "Volver", show=False),
    ]

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
        yield Header()
        yield Static("", id="status")
        with Horizontal(id="body"):
            yield OptionList(id="layout-list")
            with Vertical(id="detail"):
                yield Static("Selecciona un layout.", id="detail-name")
                yield Static("", id="detail-meta")
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh()

    def on_screen_resume(self) -> None:
        self.action_refresh()

    def action_refresh(self) -> None:
        self.layouts_dir.mkdir(parents=True, exist_ok=True)
        self._layouts = zellij_config.list_layouts(self.layouts_dir)
        option_list = self.query_one("#layout-list", OptionList)
        option_list.clear_options()
        for layout in self._layouts:
            option_list.add_option(Option(self._format(layout), id=layout.name))
        self.query_one("#status", Static).update(
            f"{len(self._layouts)} layout(s) en {self.layouts_dir}"
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
            name.update("Sin layouts.")
            meta.update("Pulsa [b]n[/b] para crear el primero.")
            return
        name.update(layout.name)
        tab_names = ", ".join((t.name or "(sin nombre)") for t in layout.tabs)
        warn = ""
        if layout.raw_unknown_nodes:
            warn = (
                "\n\nEste layout contiene nodos que el editor no entiende "
                "(p. ej. default_tab_template). Se preservan al guardar pero "
                "podrian perder formato exacto. Comentarios `/-` se descartan."
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
                    f"Nombre invalido: {name!r}. Usa letras, numeros, '-' y '_'.",
                    severity="error",
                )
                return
            target = self.layouts_dir / f"{name}.kdl"
            if target.exists():
                self.app.notify(
                    f"Ya existe {target.name}. Usa otro nombre o borra el existente.",
                    severity="error",
                )
                return
            layout = layout_ops.new_blank_layout(self.layouts_dir, name)
            kdl_io.write_layout(layout, backup=False)
            self.action_refresh()
            from ztc.screens.layout_editor import LayoutEditorScreen

            self.app.push_screen(
                LayoutEditorScreen(layout=layout, layouts_dir=self.layouts_dir)
            )

        self.app.push_screen(
            PromptModal(
                title="Nuevo layout",
                placeholder="ej. trabajo",
                confirm_label="Crear",
            ),
            after,
        )

    def action_delete(self) -> None:
        layout = self._highlighted()
        if layout is None:
            return

        def after(ok: bool) -> None:
            if not ok:
                self.app.notify("Cancelado.", severity="information")
                return
            try:
                backup = kdl_io.delete_layout(layout.path)
            except Exception as exc:  # noqa: BLE001
                self.app.notify(f"Error al borrar: {exc}", severity="error")
                return
            msg = f"Layout '{layout.name}' borrado"
            if backup is not None:
                msg += f" (backup: {backup.name})"
            self.app.notify(msg, severity="information")
            self.action_refresh()

        self.app.push_screen(
            ConfirmByNameModal(
                title="Borrar layout",
                message=f"Esto borrara el archivo {layout.path}.",
                expected=layout.name,
                confirm_label="Borrar",
            ),
            after,
        )
