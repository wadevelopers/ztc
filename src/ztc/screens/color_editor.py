from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from ztc.services import colors
from ztc.services.terminals import TerminalBackend
from ztc.widgets.confirm import EditColorModal, PromptModal
from ztc.widgets.header import StaticHeader
from ztc.zellij.config import read_active_theme
from ztc.zellij.user_themes import list_user_themes


class ColorEditorScreen(Screen[None]):
    """Editor de colores de la terminal activa.

    Lista los slots conocidos con sus valores y swatches. Permite editar uno
    por modal, ver avisos de contraste y guardar con backup. La capability
    de "importar tema desde archivo" se expone solo si el backend la soporta
    (hoy: solo Alacritty).
    """

    BINDINGS = [
        Binding("enter", "edit", "Edit"),
        Binding("x", "reset", "Reset slot"),
        Binding("i", "import", "Import theme"),
        Binding("r", "reload", "Reload"),
        Binding("s", "save", "Save"),
        Binding("escape", "back", "Back"),
        # `q` y `ctrl+q` neutralizados: solo `Esc` sale del editor.
        Binding("q", "noop", show=False),
        Binding("ctrl+q", "noop", show=False),
    ]

    def action_noop(self) -> None:
        pass

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
        yield StaticHeader()
        yield Static("", id="header-info")
        with Horizontal(id="body"):
            yield OptionList(id="slot-list")
            with Vertical(id="detail"):
                yield Static("Select a slot", id="detail-name")
                yield Static("", id="big-swatch")
                yield Static("", id="detail-meta")
        with Vertical(id="warnings-wrap"):
            yield Static("Contrast warnings", id="warnings-title")
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
            value = self.backend.read_slot(self.doc, slot) or "(unset)"
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
            meta_widget.update(f"Current value: {value}\nEnter to edit.")
        else:
            swatch_widget.update("")
            meta_widget.update(
                f"Current value: {value or '(unset)'}\nEnter to set."
            )

    def _refresh_warnings(self) -> None:
        zellij_bg: str | None = None
        active = read_active_theme(self.zellij_config_path)
        if active:
            user_themes = list_user_themes(self.zellij_config_path)
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
            widget.update("[green]No warnings.[/]")
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
                f"{slot[0]}.{slot[1]} reset (press 's' to save to disk)",
                severity="information",
                timeout=6,
            )
        else:
            self.app.notify(
                f"{slot[0]}.{slot[1]} was already unset",
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
        # `import_theme_file` esta en la TerminalBackend Protocol; cada
        # backend lo implementa para su propio formato (`.toml` para
        # Alacritty, `.conf` para Kitty). No hay cross-backend.
        backend = self.backend

        def after(path_str: str | None) -> None:
            if not path_str:
                return
            raw = Path(path_str).expanduser()
            path = raw if raw.is_absolute() else (self.backend_path.parent / raw)
            try:
                count = backend.import_theme_file(self.doc, path)
            except FileNotFoundError:
                self.app.notify(f"Does not exist: {path}", severity="error", timeout=8)
                return
            except Exception as exc:  # noqa: BLE001
                self.app.notify(f"Import error: {exc}", severity="error", timeout=10)
                return
            if count == 0:
                self.app.notify(
                    "The file contains no recognized color slots.",
                    severity="warning",
                    timeout=8,
                )
                return
            self.dirty = True
            self._refresh_header()
            self._rebuild_list()
            self._refresh_warnings()
            self.app.notify(
                f"Imported {count} slot(s) from {path.name}",
                severity="information",
                timeout=6,
            )

        self.app.push_screen(
            PromptModal(
                title="Import theme from file",
                placeholder=f"filename (next to {self.backend_path.name}) or absolute path",
                confirm_label="Import",
            ),
            after,
        )

    def action_reload(self) -> None:
        self.doc = self.backend.load(self.backend_path)
        self.dirty = False
        self._refresh_header()
        self._rebuild_list()
        self._refresh_warnings()
        self.app.notify("Reloaded from disk.", severity="information")

    def action_save(self) -> None:
        try:
            backup = self.backend.save(self.doc, self.backend_path)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Save error: {exc}", severity="error", timeout=10)
            return
        self.dirty = False
        self._refresh_header()
        msg = f"Saved: {self.backend_path.name}"
        if backup is not None:
            msg += f"  (backup: {backup.name})"
        self.app.notify(msg, severity="information", timeout=6)

    def action_back(self) -> None:
        if not self.dirty:
            self.app.pop_screen()
            return
        from ztc.widgets.confirm import UnsavedChangesModal

        def after(choice: str | None) -> None:
            if choice == "discard":
                self.app.pop_screen()
                return
            if choice == "save":
                self.action_save()
                if not self.dirty:
                    self.app.pop_screen()
                return

        self.app.push_screen(UnsavedChangesModal(), after)
