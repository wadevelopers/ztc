from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static

from term_config_tui import __version__


class TermConfigApp(App[None]):
    TITLE = "term-config-tui"
    SUB_TITLE = f"v{__version__}"

    BINDINGS = [
        ("q", "quit", "Salir"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Static("term-config-tui"),
            Static("Fase 0 - app minima. Las pantallas reales llegan en fases siguientes."),
            Static(""),
            Static("Pulsa q para salir."),
        )
        yield Footer()
