from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from term_config_tui.services import alacritty, toml_io, zellij_config, zellij_themes
from term_config_tui.widgets.confirm import EditColorModal, PromptModal


class AlacrittyColorEditorScreen(Screen[None]):
    """Editor de colores de Alacritty.

    Lista los slots conocidos con sus valores y swatches. Permite editar uno
    por modal, importar desde otro alacritty.toml, ver avisos de contraste y
    guardar con backup.
    """

    BINDINGS = [
        Binding("enter", "edit", "Editar"),
        Binding("i", "import", "Importar tema"),
        Binding("r", "reload", "Recargar"),
        Binding("ctrl+s", "save", "Guardar"),
        Binding("escape", "back", "Volver"),
        Binding("q", "back", "Volver", show=False),
    ]

    DEFAULT_CSS = """
    AlacrittyColorEditorScreen {
        layout: vertical;
    }
    #header-info {
        padding: 0 1;
        height: 1;
    }
    #body {
        height: 60%;
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
    #warnings-wrap {
        border-top: solid $panel;
        height: 1fr;
    }
    #warnings-title {
        padding: 0 1;
        color: $text-muted;
        height: 1;
    }
    #warnings {
        padding: 0 2;
    }
    """

    def __init__(self, alacritty_path: Path, zellij_config_path: Path) -> None:
        super().__init__()
        self.alacritty_path = alacritty_path
        self.zellij_config_path = zellij_config_path
        self.doc = toml_io.load_toml(alacritty_path)
        self.dirty = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="header-info")
        with Horizontal(id="body"):
            yield OptionList(id="slot-list")
            with Vertical(id="detail"):
                yield Static("Selecciona un slot", id="detail-name")
                yield Static("", id="big-swatch")
                yield Static("", id="detail-meta")
        with Vertical(id="warnings-wrap"):
            yield Static("Avisos de contraste", id="warnings-title")
            with VerticalScroll():
                yield Static("", id="warnings")
        yield Footer()

    def on_mount(self) -> None:
        self._rebuild_list()
        self._refresh_header()
        self._refresh_warnings()

    # ---------- helpers ----------

    def _refresh_header(self) -> None:
        dirty = " *" if self.dirty else ""
        self.query_one("#header-info", Static).update(
            f"[b]alacritty colors[/b]{dirty}    {self.alacritty_path}"
        )

    def _rebuild_list(self) -> None:
        option_list = self.query_one("#slot-list", OptionList)
        previous_index = option_list.highlighted
        option_list.clear_options()
        for group, name in alacritty.KNOWN_SLOTS:
            value = alacritty.read_slot(self.doc, group, name) or "(sin definir)"
            label = self._format_row(group, name, value)
            option_list.add_option(Option(label, id=f"{group}.{name}"))
        if option_list.option_count:
            option_list.highlighted = (
                previous_index
                if previous_index is not None
                and previous_index < option_list.option_count
                else 0
            )
            self._show_detail_at(option_list.highlighted)

    def _format_row(self, group: str, name: str, value: str) -> str:
        slot_label = f"{group}.{name}".ljust(22)
        swatch = f"[on {value}]      [/]" if alacritty.is_valid_hex(value) else "      "
        return f"{slot_label} {value:<10} {swatch}"

    def _show_detail_at(self, index: int | None) -> None:
        if index is None:
            return
        group, name = alacritty.KNOWN_SLOTS[index]
        value = alacritty.read_slot(self.doc, group, name)
        name_widget = self.query_one("#detail-name", Static)
        swatch_widget = self.query_one("#big-swatch", Static)
        meta_widget = self.query_one("#detail-meta", Static)
        name_widget.update(f"{group}.{name}")
        if value and alacritty.is_valid_hex(value):
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

    def _refresh_warnings(self) -> None:
        zellij_bg: str | None = None
        active = zellij_config.read_active_theme(self.zellij_config_path)
        if active:
            user_themes = zellij_themes.list_user_themes(self.zellij_config_path)
            for theme in user_themes:
                if theme.name == active:
                    for color in theme.colors:
                        if color.name == "bg" and alacritty.is_valid_hex(color.value):
                            zellij_bg = color.value
                            break
                    break
        warnings = alacritty.compute_warnings(self.doc, zellij_bg=zellij_bg)
        widget = self.query_one("#warnings", Static)
        if not warnings:
            widget.update("[green]Sin avisos.[/]")
            return
        lines = [f"- {w.message}" for w in warnings]
        widget.update("\n".join(lines))

    # ---------- eventos ----------

    @on(OptionList.OptionHighlighted, "#slot-list")
    def _on_highlight(self, event: OptionList.OptionHighlighted) -> None:
        index = self.query_one("#slot-list", OptionList).highlighted
        self._show_detail_at(index)

    @on(OptionList.OptionSelected, "#slot-list")
    def _on_select(self) -> None:
        self.action_edit()

    # ---------- acciones ----------

    def action_edit(self) -> None:
        option_list = self.query_one("#slot-list", OptionList)
        if option_list.highlighted is None:
            return
        group, name = alacritty.KNOWN_SLOTS[option_list.highlighted]
        current = alacritty.read_slot(self.doc, group, name) or ""

        def after(value: str | None) -> None:
            if value is None:
                return
            alacritty.write_slot(self.doc, group, name, value)
            self.dirty = True
            self._refresh_header()
            self._rebuild_list()
            self._refresh_warnings()

        self.app.push_screen(
            EditColorModal(slot_label=f"{group}.{name}", initial=current),
            after,
        )

    def action_import(self) -> None:
        def after(path_str: str | None) -> None:
            if not path_str:
                return
            path = Path(path_str).expanduser()
            try:
                count = alacritty.import_theme_file(self.doc, path)
            except FileNotFoundError:
                self.app.notify(f"No existe: {path}", severity="error", timeout=8)
                return
            except Exception as exc:  # noqa: BLE001
                self.app.notify(f"Error al importar: {exc}", severity="error", timeout=10)
                return
            if count == 0:
                self.app.notify(
                    "El archivo no contiene slots de color reconocidos.",
                    severity="warning",
                    timeout=8,
                )
                return
            self.dirty = True
            self._refresh_header()
            self._rebuild_list()
            self._refresh_warnings()
            self.app.notify(
                f"Importados {count} slot(s) desde {path.name}",
                severity="information",
                timeout=6,
            )

        self.app.push_screen(
            PromptModal(
                title="Importar tema desde archivo",
                placeholder="ruta a otro alacritty.toml",
                confirm_label="Importar",
            ),
            after,
        )

    def action_reload(self) -> None:
        self.doc = toml_io.load_toml(self.alacritty_path)
        self.dirty = False
        self._refresh_header()
        self._rebuild_list()
        self._refresh_warnings()
        self.app.notify("Recargado desde disco.", severity="information")

    def action_save(self) -> None:
        try:
            backup = toml_io.dump_toml(self.doc, self.alacritty_path)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Error al guardar: {exc}", severity="error", timeout=10)
            return
        self.dirty = False
        self._refresh_header()
        msg = f"Guardado: {self.alacritty_path.name}"
        if backup is not None:
            msg += f"  (backup: {backup.name})"
        self.app.notify(msg, severity="information", timeout=6)

    def action_back(self) -> None:
        if not self.dirty:
            self.app.pop_screen()
            return
        from term_config_tui.widgets.confirm import ConfirmByNameModal

        def after(ok: bool) -> None:
            if ok:
                self.app.pop_screen()

        self.app.push_screen(
            ConfirmByNameModal(
                title="Hay cambios sin guardar",
                message=(
                    "Si vuelves ahora, perderas los cambios. "
                    "Cancela y pulsa Ctrl+S para guardar."
                ),
                expected="descartar",
                confirm_label="Descartar cambios",
            ),
            after,
        )
