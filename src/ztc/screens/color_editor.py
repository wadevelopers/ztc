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
from ztc.services.profile_io import resolve_profile_path, validate_profile_path
from ztc.services.save_helper import compose_save_toast, save_profile_with_reload
from ztc.services.terminals import TerminalBackend
from ztc.widgets.confirm import (
    ConfirmActionModal,
    EditColorModal,
    PromptModal,
    UnsavedChangesModal,
)
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
        Binding("r", "reload", "Reload"),
        Binding("l", "load", "Load"),
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

    def action_load(self) -> None:
        """Carga un perfil desde archivo y lo deja como activo: escribe
        el manifest apuntando al nuevo perfil y aplica al terminal vivo
        via `set_active_profile`. Si hay cambios sin guardar, pide
        confirmacion antes (descartarlos perderia trabajo)."""
        if self.dirty:
            manifest_path = self.app.backend_manifest_path

            def after_dirty(choice: str | None) -> None:
                if choice == "discard":
                    self._prompt_load_profile()
                elif choice == "save" and manifest_path is not None:
                    # Save in-place al activo: el user ya eligio "save"
                    # en el modal, no abrimos un segundo modal de nombre.
                    self._save_in_place(manifest_path)
                    if not self.dirty:
                        self._prompt_load_profile()

            self.app.push_screen(UnsavedChangesModal(), after_dirty)
            return
        self._prompt_load_profile()

    def _prompt_load_profile(self) -> None:
        manifest_path = self.app.backend_manifest_path
        if manifest_path is None:
            return

        def after(path_str: str | None) -> None:
            if not path_str:
                return
            raw = Path(path_str).expanduser()
            path = raw if raw.is_absolute() else (manifest_path.parent / raw)
            if not path.exists():
                self.app.notify(
                    f"Does not exist: {path}", severity="error", timeout=8
                )
                return
            if path == manifest_path:
                # `include kitty.conf` dentro de `kitty.conf` = recursion
                # infinita al reload. El manifest no es perfil cargable.
                self.app.notify(
                    f"Cannot load the manifest file ({manifest_path.name}) "
                    "as a profile; choose another.",
                    severity="error",
                    timeout=8,
                )
                return
            self._do_load(path, manifest_path)

        self.app.push_screen(
            PromptModal(
                title="Load profile from file",
                placeholder=f"filename (next to {manifest_path.name}) or absolute path",
                confirm_label="Load",
            ),
            after,
        )

    def _do_load(self, path: Path, manifest_path: Path) -> None:
        """Carga `path` como perfil activo. Si el manifest aun no esta
        gestionado, lo convierte primero (silencioso, con backup
        automatico) y luego carga. El backup del estado pre-conversion
        queda cargable directo desde Load con su nombre."""
        convert_backup: Path | None = None
        if not self.backend.is_managed_manifest(manifest_path):
            try:
                convert_backup = self.backend.convert_to_manifest(
                    manifest_path, path
                )
            except Exception as exc:  # noqa: BLE001
                self.app.notify(
                    f"Convert error: {exc}", severity="error", timeout=10
                )
                return
        try:
            new_doc = self.backend.load(path)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Load error: {exc}", severity="error", timeout=10)
            return
        try:
            self.app.set_active_profile(path)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(
                f"Profile switch error: {exc}", severity="error", timeout=10
            )
            return
        self.doc = new_doc
        self.backend_path = path
        self.dirty = False
        self._refresh_header()
        self._rebuild_list()
        self._refresh_warnings()
        msg = f"Loaded {path.name}"
        if convert_backup is not None:
            msg += f"  (previous setup: {convert_backup.name})"
        self.app.notify(msg, severity="information", timeout=6)

    def action_reload(self) -> None:
        self.doc = self.backend.load(self.backend_path)
        self.dirty = False
        self._refresh_header()
        self._rebuild_list()
        self._refresh_warnings()
        self.app.notify("Reloaded from disk.", severity="information")

    def action_save(self) -> None:
        """Abre Save modal prellenado con el nombre actual.
        - Enter directo con mismo nombre → save in-place sobre el activo.
        - Nombre nuevo → save-as: crea archivo, set_active_profile, switch.
        Si el archivo destino existe y no es el activo, confirma overwrite.
        Si todavia no hay manifest, dispara G2 antes del save-as."""
        manifest_path = self.app.backend_manifest_path
        if manifest_path is None:
            return

        def after(name: str | None) -> None:
            if not name:
                return
            new_path = resolve_profile_path(name, manifest_path.parent)
            # Save-in-place sobre el activo: no aplica validacion. Caso
            # standalone (backend_path == manifest_path) cae aca y es OK
            # — es save normal sobre el archivo default sin convertir.
            if new_path == self.backend_path:
                self._save_in_place(manifest_path)
                return
            error = validate_profile_path(
                self.backend, new_path, manifest_path=manifest_path
            )
            if error:
                self.app.notify(error, severity="error", timeout=8)
                return
            if new_path.exists():
                def after_confirm(confirmed: bool | None) -> None:
                    if confirmed:
                        self._save_as(new_path, manifest_path)
                self.app.push_screen(
                    ConfirmActionModal(
                        title="Overwrite file?",
                        message=f"{new_path} already exists.",
                        confirm_label="Overwrite",
                    ),
                    after_confirm,
                )
                return
            self._save_as(new_path, manifest_path)

        self.app.push_screen(
            PromptModal(
                title="Save profile",
                initial=self.backend_path.name,
                confirm_label="Save",
            ),
            after,
        )

    def _save_in_place(self, manifest_path: Path) -> None:
        """Save al perfil activo. Usa `save_profile_with_reload` para que
        en Kitty el reload IPC lea las prefs runtime del manifest (no del
        perfil)."""
        try:
            result = save_profile_with_reload(
                self.backend, self.doc, self.backend_path, manifest_path
            )
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Save error: {exc}", severity="error", timeout=10)
            return
        self.dirty = False
        self._refresh_header()
        self.app.notify(
            compose_save_toast(self.backend_path.name, result),
            severity="information",
            timeout=6,
        )

    def _save_as(self, new_path: Path, manifest_path: Path) -> None:
        """Save-as a archivo nuevo. Si el manifest aun no esta gestionado,
        lo convierte silenciosamente primero (backup automatico) y luego
        guarda el doc in-memory al new_path."""
        convert_backup: Path | None = None
        if not self.backend.is_managed_manifest(manifest_path):
            try:
                convert_backup = self.backend.convert_to_manifest(
                    manifest_path, new_path
                )
            except Exception as exc:  # noqa: BLE001
                self.app.notify(
                    f"Convert error: {exc}", severity="error", timeout=10
                )
                return
        try:
            self.backend.save(self.doc, new_path)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Save error: {exc}", severity="error", timeout=10)
            return
        try:
            self.app.set_active_profile(new_path)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(
                f"Profile switch error: {exc}", severity="error", timeout=10
            )
            return
        self.backend_path = new_path
        self.dirty = False
        self._refresh_header()
        msg = f"Saved as {new_path.name}"
        if convert_backup is not None:
            msg += f"  (previous setup: {convert_backup.name})"
        self.app.notify(msg, severity="information", timeout=6)

    def action_back(self) -> None:
        if not self.dirty:
            self.app.pop_screen()
            return
        manifest_path = self.app.backend_manifest_path

        def after(choice: str | None) -> None:
            if choice == "discard":
                self.app.pop_screen()
                return
            if choice == "save" and manifest_path is not None:
                # Save in-place sobre el activo, sin modal de nombre: el
                # user ya eligio "save" para volver.
                self._save_in_place(manifest_path)
                if not self.dirty:
                    self.app.pop_screen()
                return

        self.app.push_screen(UnsavedChangesModal(), after)
