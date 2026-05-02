from __future__ import annotations

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from term_config_tui import __version__
from term_config_tui.models.config import Paths
from term_config_tui.screens.color_editor import AlacrittyColorEditorScreen
from term_config_tui.screens.layout_list import LayoutListScreen
from term_config_tui.screens.session_manager import SessionManagerScreen
from term_config_tui.screens.theme_editor import ThemePickerScreen
from term_config_tui.services import zellij_config, zellij_themes


class TermConfigApp(App[None]):
    TITLE = "term-config-tui"
    SUB_TITLE = f"v{__version__}"

    BINDINGS = [
        Binding("p", "command_palette", "Buscar"),
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
                Option("Sesiones Zellij", id="sessions"),
                Option("Layouts Zellij", id="layouts"),
                Option("Colores Alacritty", id="colors"),
                id="main-menu",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.sync_theme_with_zellij()
        self.query_one("#main-menu", OptionList).focus()

    def sync_theme_with_zellij(self) -> None:
        """Aplica el tema Textual que matchea el tema Zellij activo."""
        active = zellij_config.read_active_theme(self.paths.zellij_config)
        self.apply_theme_for_zellij(active)

    def apply_theme_for_zellij(self, zellij_name: str | None) -> None:
        """Cambia el tema del TUI al equivalente Textual del tema Zellij dado."""
        target = zellij_themes.textual_theme_for(zellij_name)
        if target in self.available_themes and self.theme != target:
            self.theme = target

    @on(OptionList.OptionSelected, "#main-menu")
    def _on_menu_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "themes":
            self.push_screen(ThemePickerScreen(config_path=self.paths.zellij_config))
        elif event.option.id == "sessions":
            self.push_screen(SessionManagerScreen(layouts_dir=self.paths.zellij_layouts_dir))
        elif event.option.id == "layouts":
            self.push_screen(LayoutListScreen(layouts_dir=self.paths.zellij_layouts_dir))
        elif event.option.id == "colors":
            self.push_screen(
                AlacrittyColorEditorScreen(
                    alacritty_path=self.paths.alacritty_config,
                    zellij_config_path=self.paths.zellij_config,
                )
            )
