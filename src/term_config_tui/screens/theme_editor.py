from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from term_config_tui.models.theme import ZellijTheme
from term_config_tui.services import zellij_config, zellij_themes


class ThemePickerScreen(Screen[None]):
    """Pantalla para elegir el tema activo de Zellij."""

    BINDINGS = [
        Binding("enter", "apply", "Aplicar", show=True),
        Binding("escape", "app.pop_screen", "Volver", show=True),
        Binding("q", "app.pop_screen", "Volver", show=False),
    ]

    DEFAULT_CSS = """
    ThemePickerScreen {
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
    #info {
        padding: 1 2;
        height: 1fr;
    }
    #info-name {
        text-style: bold;
        color: $accent;
    }
    .swatch-row {
        height: 1;
    }
    """

    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config_path = config_path
        self._themes: list[ZellijTheme] = []
        self._active: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="status")
        with Horizontal(id="body"):
            yield OptionList(id="theme-list")
            with Vertical(id="info"):
                yield Static("Selecciona un tema para ver detalles.", id="info-name")
                yield Static("", id="info-meta")
                yield Static("", id="info-colors")
        yield Footer()

    def on_mount(self) -> None:
        self._reload()

    def _reload(self) -> None:
        self._themes = zellij_themes.list_all_themes(self.config_path)
        self._active = zellij_config.read_active_theme(self.config_path)
        self._refresh_status()

        option_list = self.query_one("#theme-list", OptionList)
        option_list.clear_options()
        active_index = 0
        for i, theme in enumerate(self._themes):
            label = self._format_option(theme)
            option_list.add_option(Option(label, id=theme.name))
            if theme.name == self._active:
                active_index = i
        if self._themes:
            option_list.highlighted = active_index
            self._show_info(self._themes[active_index])

    def _format_option(self, theme: ZellijTheme) -> str:
        marker = "* " if theme.name == self._active else "  "
        tag = "[user]" if theme.is_user else "[builtin]"
        return f"{marker}{theme.name:<24} {tag}"

    def _refresh_status(self) -> None:
        status = self.query_one("#status", Static)
        active = self._active or "(ninguno)"
        status.update(
            f"Tema activo: [b]{active}[/b]    config: {self.config_path}"
        )

    def _show_info(self, theme: ZellijTheme) -> None:
        name_widget = self.query_one("#info-name", Static)
        meta_widget = self.query_one("#info-meta", Static)
        colors_widget = self.query_one("#info-colors", Static)

        name_widget.update(theme.name)
        kind = "user-defined" if theme.is_user else "built-in"
        active_marker = "  (activo)" if theme.name == self._active else ""
        meta_widget.update(f"Tipo: {kind}{active_marker}")

        if theme.colors:
            lines = []
            for color in theme.colors:
                if _looks_like_hex(color.value):
                    swatch = f"[on {color.value}]      [/]"
                else:
                    swatch = "      "
                lines.append(f"{color.name:<20} {color.value:<10} {swatch}")
            colors_widget.update("\n".join(lines))
        else:
            colors_widget.update(
                "Sin preview de colores: los temas built-in los resuelve Zellij\n"
                "en tiempo de ejecucion. Pulsa Enter para aplicar."
            )

    @on(OptionList.OptionHighlighted, "#theme-list")
    def _on_highlight(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is None:
            return
        theme = self._theme_by_name(event.option.id)
        if theme is not None:
            self._show_info(theme)

    @on(OptionList.OptionSelected, "#theme-list")
    def _on_select(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return
        self._apply(event.option.id)

    def action_apply(self) -> None:
        option_list = self.query_one("#theme-list", OptionList)
        if option_list.highlighted is None:
            return
        option = option_list.get_option_at_index(option_list.highlighted)
        if option.id is not None:
            self._apply(option.id)

    def _apply(self, name: str) -> None:
        if name == self._active:
            self.app.notify(f"'{name}' ya es el tema activo", severity="information")
            return
        try:
            backup = zellij_config.set_active_theme(self.config_path, name)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Error al aplicar tema: {exc}", severity="error", timeout=8)
            return
        msg = f"Tema cambiado a '{name}'"
        if backup is not None:
            msg += f" (backup: {backup.name})"
        self.app.notify(msg, severity="information", timeout=6)
        self._reload()

    def _theme_by_name(self, name: str) -> ZellijTheme | None:
        return next((t for t in self._themes if t.name == name), None)


def _looks_like_hex(value: str) -> bool:
    if not value.startswith("#"):
        return False
    rest = value[1:]
    return len(rest) in (3, 6, 8) and all(c in "0123456789abcdefABCDEF" for c in rest)
