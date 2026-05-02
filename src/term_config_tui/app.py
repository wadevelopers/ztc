from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static

from term_config_tui import __version__
from term_config_tui.models.config import Paths
from term_config_tui.screens.theme_editor import ThemePickerScreen


class TermConfigApp(App[None]):
    TITLE = "term-config-tui"
    SUB_TITLE = f"v{__version__}"

    BINDINGS = [
        Binding("t", "theme_picker", "Tema Zellij"),
        Binding("q", "quit", "Salir"),
    ]

    DEFAULT_CSS = """
    #menu {
        padding: 1 2;
    }
    .menu-title {
        text-style: bold;
        color: $accent;
    }
    .menu-item {
        margin-top: 1;
    }
    .menu-key {
        color: $accent;
        text-style: bold;
    }
    """

    def __init__(self, paths: Paths | None = None) -> None:
        super().__init__()
        self.paths = paths or Paths.default()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Static("term-config-tui", classes="menu-title"),
            Static("", classes="menu-item"),
            Static("[b]t[/b]  Tema Zellij", classes="menu-item"),
            Static("[dim]s[/dim]  Sesiones Zellij (proxima fase)", classes="menu-item"),
            Static("[dim]l[/dim]  Layouts Zellij (proxima fase)", classes="menu-item"),
            Static("[dim]c[/dim]  Colores Alacritty (proxima fase)", classes="menu-item"),
            Static("", classes="menu-item"),
            Static("[b]q[/b]  Salir", classes="menu-item"),
            id="menu",
        )
        yield Footer()

    def action_theme_picker(self) -> None:
        self.push_screen(ThemePickerScreen(config_path=self.paths.zellij_config))
