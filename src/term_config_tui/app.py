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
from term_config_tui.screens.theme_editor import ThemePickerScreen
from term_config_tui.services import zellij_config, zellij_theme_assets, zellij_themes


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
                Option("Layouts Zellij", id="layouts"),
                Option("Colores Alacritty", id="colors"),
                id="main-menu",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.register_zellij_themes()
        self.sync_theme_with_zellij()
        self.query_one("#main-menu", OptionList).focus()

    def register_zellij_themes(self) -> None:
        """Registra como temas de Textual los built-in vendorizados y los
        user themes definidos en config.kdl. Idempotente: re-registra
        cuando el usuario crea/edita user themes.
        """
        # Built-in vendorizados.
        for ui_theme in zellij_theme_assets.load_all_bundled_themes():
            textual_theme = zellij_theme_assets.build_textual_theme(ui_theme)
            if textual_theme is not None:
                self.register_theme(textual_theme)
        # User themes: si tienen raw_components (modo always-save), usamos el
        # mismo builder rich-based para que primary/accent/etc. salgan iguales
        # que en el built-in equivalente. Fallback al builder legacy si no hay
        # rich (caso raro: tema editado a mano sin bloques ricos).
        for ut in zellij_themes.list_user_themes(self.paths.zellij_config):
            ui_theme = zellij_theme_assets.user_theme_to_ui_theme(ut)
            textual_theme = (
                zellij_theme_assets.build_textual_theme(ui_theme)
                if ui_theme is not None
                else zellij_theme_assets.build_textual_theme_from_legacy(
                    ut.name, {c.name: c.value for c in ut.colors}
                )
            )
            if textual_theme is not None:
                self.register_theme(textual_theme)

    def sync_theme_with_zellij(self) -> None:
        """Aplica el tema Textual con el mismo nombre que el tema Zellij activo."""
        active = zellij_config.read_active_theme(self.paths.zellij_config)
        self.apply_theme_for_zellij(active)

    def apply_theme_for_zellij(self, zellij_name: str | None) -> None:
        """Cambia el tema del TUI al que tenga el mismo nombre que el de Zellij.

        Si el nombre no esta registrado (built-in nuevo no vendorizado, o
        user theme con problemas de parseo), cae a `textual-dark`.

        Si el target ya es el tema activo, igualmente se fuerza un re-apply
        invocando el watcher de Textual a mano, para que recoja los hex
        actualizados del Theme registrado (caso: editar el user theme activo
        y guardar — sin esto el TUI no se refrescaria hasta reiniciar).
        """
        target = zellij_name if zellij_name else zellij_themes.TEXTUAL_FALLBACK
        if target not in self.available_themes:
            target = zellij_themes.TEXTUAL_FALLBACK
        if self.theme != target:
            self.theme = target
        else:
            # Forzar refresh manualmente: Textual no dispara el watcher si
            # el valor del reactive no cambia, pero el Theme registrado SI
            # puede haber cambiado (ej. user theme editado).
            self._watch_theme(target)

    @on(OptionList.OptionSelected, "#main-menu")
    def _on_menu_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "themes":
            self.push_screen(ThemePickerScreen(config_path=self.paths.zellij_config))
        elif event.option.id == "layouts":
            self.push_screen(LayoutListScreen(layouts_dir=self.paths.zellij_layouts_dir))
        elif event.option.id == "colors":
            self.push_screen(
                AlacrittyColorEditorScreen(
                    alacritty_path=self.paths.alacritty_config,
                    zellij_config_path=self.paths.zellij_config,
                )
            )
