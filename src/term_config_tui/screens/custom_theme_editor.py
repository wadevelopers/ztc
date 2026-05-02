from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from term_config_tui.models.theme import ZellijColor, ZellijTheme
from term_config_tui.services import zellij_themes
from term_config_tui.widgets.confirm import (
    ConfirmByNameModal,
    EditColorModal,
)


class CustomThemeEditorScreen(Screen[None]):
    """Edita los slots de color de un user theme y los guarda en config.kdl."""

    BINDINGS = [
        Binding("enter", "edit", "Editar slot"),
        Binding("ctrl+s", "save", "Guardar"),
        Binding("escape", "back", "Volver"),
        Binding("q", "back", "Volver", show=False),
    ]

    DEFAULT_CSS = """
    CustomThemeEditorScreen {
        layout: vertical;
    }
    #header-info {
        padding: 0 1;
        height: 1;
    }
    #body {
        height: 1fr;
    }
    OptionList {
        width: 50;
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
    #big-swatch {
        height: 5;
        margin: 1 0;
    }
    """

    def __init__(self, config_path: Path, theme: ZellijTheme) -> None:
        super().__init__()
        self.config_path = config_path
        # Trabajamos sobre una copia mutable para no afectar el modelo origen.
        self.theme = ZellijTheme(
            name=theme.name,
            source="user",
            colors=list(theme.colors),
        )
        self.dirty = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="header-info")
        with Horizontal(id="body"):
            yield OptionList(id="slot-list")
            with Vertical(id="detail"):
                yield Static("", id="detail-name")
                yield Static("", id="big-swatch")
                yield Static("", id="detail-meta")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_header()
        self._rebuild_list()

    # ---------- helpers ----------

    def _refresh_header(self) -> None:
        dirty = " *" if self.dirty else ""
        self.query_one("#header-info", Static).update(
            f"[b]theme: {self.theme.name}[/b]{dirty}    {self.config_path}"
        )

    def _all_slot_names(self) -> list[str]:
        """Slots a mostrar: legacy estandar + cualquier extra que tenga el tema."""
        defined = {c.name for c in self.theme.colors}
        ordered = list(zellij_themes.LEGACY_SLOTS)
        for name in defined:
            if name not in ordered:
                ordered.append(name)
        return ordered

    def _value_for(self, slot: str) -> str | None:
        for c in self.theme.colors:
            if c.name == slot:
                return c.value
        return None

    def _rebuild_list(self) -> None:
        option_list = self.query_one("#slot-list", OptionList)
        prev = option_list.highlighted
        option_list.clear_options()
        for slot in self._all_slot_names():
            value = self._value_for(slot) or "(sin definir)"
            label = self._format_row(slot, value)
            option_list.add_option(Option(label, id=slot))
        if option_list.option_count:
            option_list.highlighted = (
                prev if prev is not None and prev < option_list.option_count else 0
            )
            self._show_detail_at(option_list.highlighted)

    def _format_row(self, slot: str, value: str) -> str:
        swatch = f"[on {value}]      [/]" if value.startswith("#") else "      "
        return f"{slot:<14} {value:<10} {swatch}"

    def _show_detail_at(self, index: int | None) -> None:
        if index is None:
            return
        slot = self._all_slot_names()[index]
        value = self._value_for(slot)
        name_widget = self.query_one("#detail-name", Static)
        swatch_widget = self.query_one("#big-swatch", Static)
        meta_widget = self.query_one("#detail-meta", Static)
        name_widget.update(slot)
        if value and value.startswith("#"):
            big = "\n".join(
                [f"[on {value}]                                                  [/]"] * 3
            )
            swatch_widget.update(big)
            meta_widget.update(f"Valor actual: {value}\nEnter para editar.")
        else:
            swatch_widget.update("")
            meta_widget.update(
                f"Valor actual: {value or '(sin definir)'}\nEnter para definir."
            )

    @on(OptionList.OptionHighlighted, "#slot-list")
    def _on_highlight(self, event: OptionList.OptionHighlighted) -> None:
        self._show_detail_at(self.query_one("#slot-list", OptionList).highlighted)

    @on(OptionList.OptionSelected, "#slot-list")
    def _on_select(self) -> None:
        self.action_edit()

    # ---------- acciones ----------

    def action_edit(self) -> None:
        option_list = self.query_one("#slot-list", OptionList)
        if option_list.highlighted is None:
            return
        slot = self._all_slot_names()[option_list.highlighted]
        current = self._value_for(slot) or ""

        def after(value: str | None) -> None:
            if value is None:
                return
            # Reemplaza o anade el slot.
            for i, c in enumerate(self.theme.colors):
                if c.name == slot:
                    self.theme.colors[i] = ZellijColor(name=slot, value=value)
                    break
            else:
                self.theme.colors.append(ZellijColor(name=slot, value=value))
            self.dirty = True
            self._refresh_header()
            self._rebuild_list()

        self.app.push_screen(
            EditColorModal(slot_label=f"{self.theme.name}.{slot}", initial=current),
            after,
        )

    def action_save(self) -> None:
        try:
            backup = zellij_themes.upsert_user_theme(self.config_path, self.theme)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Error al guardar: {exc}", severity="error", timeout=10)
            return
        self.dirty = False
        self._refresh_header()
        msg = f"Tema '{self.theme.name}' guardado en config.kdl"
        if backup is not None:
            msg += f"  (backup: {backup.name})"
        self.app.notify(msg, severity="information", timeout=6)

    def action_back(self) -> None:
        if not self.dirty:
            self.app.pop_screen()
            return

        def after(ok: bool) -> None:
            if ok:
                self.app.pop_screen()

        self.app.push_screen(
            ConfirmByNameModal(
                title="Hay cambios sin guardar",
                message=(
                    "Si vuelves ahora, perderas los cambios del tema. "
                    "Cancela y pulsa Ctrl+S para guardar."
                ),
                expected="descartar",
                confirm_label="Descartar cambios",
            ),
            after,
        )
