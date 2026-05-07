from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from zellij_themes import colors

from term_config_tui.services import zellij_config, zellij_themes
from term_config_tui.services.terminals import TerminalBackend
from term_config_tui.services.terminals.alacritty import AlacrittyBackend
from term_config_tui.widgets.confirm import EditColorModal, PromptModal


class ColorEditorScreen(Screen[None]):
    """Editor de colores de la terminal activa.

    Lista los slots conocidos con sus valores y swatches. Permite editar uno
    por modal, ver avisos de contraste y guardar con backup. La capability
    de "importar tema desde archivo" se expone solo si el backend la soporta
    (hoy: solo Alacritty).
    """

    BINDINGS = [
        Binding("enter", "edit", "Editar"),
        Binding("x", "reset", "Resetear slot"),
        Binding("i", "import", "Importar tema"),
        Binding("r", "reload", "Recargar"),
        Binding("s", "save", "Guardar"),
        Binding("escape", "back", "Volver"),
        Binding("q", "back", "Volver", show=False),
    ]

    DEFAULT_CSS = """
    ColorEditorScreen {
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

    def __init__(
        self,
        backend: TerminalBackend,
        backend_path: Path,
        zellij_config_path: Path,
    ) -> None:
        super().__init__()
        self.backend = backend
        self.backend_path = backend_path
        self.zellij_config_path = zellij_config_path
        self.slots = backend.supported_slots()
        self.doc = backend.load(backend_path)
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
            f"[b]{self.backend.display_name} colors[/b]{dirty}    {self.backend_path}"
        )

    def _rebuild_list(self) -> None:
        option_list = self.query_one("#slot-list", OptionList)
        previous_index = option_list.highlighted
        option_list.clear_options()
        for slot in self.slots:
            value = self.backend.read_slot(self.doc, slot) or "(sin definir)"
            label = self._format_row(slot[0], slot[1], value)
            option_list.add_option(Option(label, id=f"{slot[0]}.{slot[1]}"))
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
        swatch = f"[on {value}]      [/]" if colors.is_valid_hex(value) else "      "
        return f"{slot_label} {value:<10} {swatch}"

    def _show_detail_at(self, index: int | None) -> None:
        if index is None:
            return
        slot = self.slots[index]
        group, name = slot
        value = self.backend.read_slot(self.doc, slot)
        name_widget = self.query_one("#detail-name", Static)
        swatch_widget = self.query_one("#big-swatch", Static)
        meta_widget = self.query_one("#detail-meta", Static)
        name_widget.update(f"{group}.{name}")
        if value and colors.is_valid_hex(value):
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
                        if color.name == "bg" and colors.is_valid_hex(color.value):
                            zellij_bg = color.value
                            break
                    break
        slot_values = {
            slot: value
            for slot in self.slots
            for value in [self.backend.read_slot(self.doc, slot)]
            if value is not None
        }
        warnings = colors.compute_warnings(slot_values, zellij_bg=zellij_bg)
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

    def action_reset(self) -> None:
        """Borra el slot del archivo para que vuelva a estar 'sin definir'."""
        option_list = self.query_one("#slot-list", OptionList)
        if option_list.highlighted is None:
            return
        slot = self.slots[option_list.highlighted]
        if self.backend.delete_slot(self.doc, slot):
            self.dirty = True
            self._refresh_header()
            self._rebuild_list()
            self._refresh_warnings()
            self.app.notify(
                f"{slot[0]}.{slot[1]} reseteado (pulsa 's' para guardar al disco)",
                severity="information",
                timeout=6,
            )
        else:
            self.app.notify(
                f"{slot[0]}.{slot[1]} ya estaba sin definir",
                severity="information",
            )

    def action_edit(self) -> None:
        option_list = self.query_one("#slot-list", OptionList)
        if option_list.highlighted is None:
            return
        slot = self.slots[option_list.highlighted]
        current = self.backend.read_slot(self.doc, slot) or ""

        def after(value: str | None) -> None:
            if value is None:
                return
            self.backend.write_slot(self.doc, slot, value)
            self.dirty = True
            self._refresh_header()
            self._rebuild_list()
            self._refresh_warnings()

        self.app.push_screen(
            EditColorModal(slot_label=f"{slot[0]}.{slot[1]}", initial=current),
            after,
        )

    def action_import(self) -> None:
        # Capability solo de Alacritty: import desde otro alacritty.toml.
        if not isinstance(self.backend, AlacrittyBackend):
            self.app.notify(
                f"Importar tema no soportado en {self.backend.display_name}.",
                severity="warning",
                timeout=6,
            )
            return
        backend = self.backend  # narrowing para el closure

        def after(path_str: str | None) -> None:
            if not path_str:
                return
            raw = Path(path_str).expanduser()
            path = raw if raw.is_absolute() else (self.backend_path.parent / raw)
            try:
                count = backend.import_theme_file(self.doc, path)
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
                title=f"Importar tema desde archivo",
                placeholder=f"nombre de archivo (junto a {self.backend_path.name}) o ruta absoluta",
                confirm_label="Importar",
            ),
            after,
        )

    def action_reload(self) -> None:
        self.doc = self.backend.load(self.backend_path)
        self.dirty = False
        self._refresh_header()
        self._rebuild_list()
        self._refresh_warnings()
        self.app.notify("Recargado desde disco.", severity="information")

    def action_save(self) -> None:
        try:
            backup = self.backend.save(self.doc, self.backend_path)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Error al guardar: {exc}", severity="error", timeout=10)
            return
        self.dirty = False
        self._refresh_header()
        msg = f"Guardado: {self.backend_path.name}"
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
