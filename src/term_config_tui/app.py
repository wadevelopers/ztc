from __future__ import annotations

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from term_config_tui import __version__
from term_config_tui.models.config import Paths
from term_config_tui.screens.theme_editor import ThemePickerScreen


class TermConfigApp(App[None]):
    TITLE = "term-config-tui"
    SUB_TITLE = f"v{__version__}"

    BINDINGS = [
        Binding("q", "quit", "Salir"),
    ]

    DEFAULT_CSS = """
    #menu-wrap {
        padding: 1 2;
    }
    .menu-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    .menu-hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    #main-menu {
        height: auto;
        max-height: 20;
        border: round $panel;
    }
    """

    def __init__(self, paths: Paths | None = None) -> None:
        super().__init__()
        self.paths = paths or Paths.default()

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="menu-wrap"):
            yield Static("term-config-tui", classes="menu-title")
            yield Static(
                "Flechas para navegar  /  Enter para abrir  /  q para salir",
                classes="menu-hint",
            )
            yield OptionList(
                Option("Tema Zellij", id="themes"),
                Option("Sesiones Zellij  (proxima fase)", id="sessions", disabled=True),
                Option("Layouts Zellij  (proxima fase)", id="layouts", disabled=True),
                Option("Colores Alacritty  (proxima fase)", id="colors", disabled=True),
                id="main-menu",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#main-menu", OptionList).focus()

    @on(OptionList.OptionSelected, "#main-menu")
    def _on_menu_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "themes":
            self.push_screen(ThemePickerScreen(config_path=self.paths.zellij_config))
