"""Editor de settings de la terminal activa: padding, opacity, font,
cursor shape. Cubre los settings comunes con mapeo limpio entre
backends (Alacritty TOML y Kitty conf). Paralelo a `ColorEditorScreen`.
"""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from ztc.services.fonts import list_monospace_fonts
from ztc.services.terminals import TerminalBackend
from ztc.services.terminals.alacritty import AlacrittyBackend
from ztc.services.terminals.settings import (
    CanonicalSetting,
    SettingKind,
    coerce_setting_value,
)
from ztc.widgets.confirm import EnumPickerModal, FontPickerModal, PromptModal


class TerminalSettingsScreen(Screen[None]):
    """Editor de settings (no-color) del backend activo: padding,
    opacity, font size, font family, cursor shape.
    """

    BINDINGS = [
        Binding("enter", "edit", "Edit"),
        Binding("x", "reset", "Reset"),
        Binding("i", "import", "Import"),
        Binding("r", "reload", "Reload"),
        Binding("s", "save", "Save"),
        Binding("escape", "back", "Back"),
        Binding("q", "back", "Back", show=False),
    ]

    DEFAULT_CSS = """
    TerminalSettingsScreen {
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
    """

    def __init__(
        self,
        backend: TerminalBackend,
        backend_path: Path,
    ) -> None:
        super().__init__()
        self.backend = backend
        self.backend_path = backend_path
        self.settings: list[CanonicalSetting] = backend.supported_settings()
        self.doc = backend.load(backend_path)
        self.dirty = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="header-info")
        with Horizontal(id="body"):
            yield OptionList(id="setting-list")
            with Vertical(id="detail"):
                yield Static("Select a setting", id="detail-name")
                yield Static("", id="detail-meta")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_header()
        self._rebuild_list()

    # ---------- helpers ----------

    def _refresh_header(self) -> None:
        dirty = " *" if self.dirty else ""
        self.query_one("#header-info", Static).update(
            f"[b]{self.backend.display_name} settings[/b]{dirty}    {self.backend_path}"
        )

    def _rebuild_list(self) -> None:
        option_list = self.query_one("#setting-list", OptionList)
        previous_index = option_list.highlighted
        option_list.clear_options()
        for setting in self.settings:
            value = self.backend.read_setting(self.doc, setting)
            display = self._format_value(value)
            label = self._format_row(setting.name, display)
            option_list.add_option(Option(label, id=setting.name))
        if option_list.option_count:
            option_list.highlighted = (
                previous_index
                if previous_index is not None
                and previous_index < option_list.option_count
                else 0
            )
            self._show_detail_at(option_list.highlighted)

    def _format_row(self, name: str, value: str) -> str:
        return f"{name:<22} {value}"

    def _format_value(self, value: object | None) -> str:
        if value is None:
            return "(unset)"
        return str(value)

    def _show_detail_at(self, index: int | None) -> None:
        if index is None:
            return
        setting = self.settings[index]
        value = self.backend.read_setting(self.doc, setting)
        name_widget = self.query_one("#detail-name", Static)
        meta_widget = self.query_one("#detail-meta", Static)
        name_widget.update(setting.name)
        kind_label = setting.kind.value
        if setting.kind == SettingKind.ENUM:
            kind_label = f"enum [{', '.join(setting.enum_values)}]"
        elif setting.kind in (SettingKind.INT, SettingKind.FLOAT):
            range_parts = []
            if setting.min_value is not None:
                range_parts.append(f"min={setting.min_value}")
            if setting.max_value is not None:
                range_parts.append(f"max={setting.max_value}")
            if range_parts:
                kind_label = f"{kind_label} ({', '.join(range_parts)})"
        lines = [
            f"Type: {kind_label}",
            f"Default: {setting.default}",
            f"Current: {self._format_value(value)}",
        ]
        meta_widget.update("\n".join(lines))

    # ---------- eventos ----------

    @on(OptionList.OptionHighlighted, "#setting-list")
    def _on_highlight(self, event: OptionList.OptionHighlighted) -> None:
        index = self.query_one("#setting-list", OptionList).highlighted
        self._show_detail_at(index)

    @on(OptionList.OptionSelected, "#setting-list")
    def _on_select(self) -> None:
        self.action_edit()

    # ---------- acciones ----------

    def action_edit(self) -> None:
        option_list = self.query_one("#setting-list", OptionList)
        if option_list.highlighted is None:
            return
        setting = self.settings[option_list.highlighted]
        current = self.backend.read_setting(self.doc, setting)

        def after(raw: str | None) -> None:
            if raw is None:
                return
            value = coerce_setting_value(setting, raw)
            if value is None:
                self.app.notify(
                    f"Invalid value for {setting.name}: {raw!r}",
                    severity="error",
                    timeout=6,
                )
                return
            try:
                self.backend.write_setting(self.doc, setting, value)
            except ValueError as exc:
                self.app.notify(f"Invalid: {exc}", severity="error", timeout=6)
                return
            self.dirty = True
            self._refresh_header()
            self._rebuild_list()

        if setting.kind == SettingKind.ENUM:
            self.app.push_screen(
                EnumPickerModal(
                    title=f"Edit {setting.name}",
                    choices=setting.enum_values,
                    initial=str(current) if current is not None else None,
                ),
                after,
            )
        elif setting.name == "font.family":
            # Picker con fuentes monoespaciadas detectadas en el sistema
            # via fontconfig. Si no hay fontconfig (lista vacia), fallback
            # a input de texto libre.
            fonts = list_monospace_fonts()
            if fonts:
                self.app.push_screen(
                    FontPickerModal(
                        title=f"Edit {setting.name}",
                        choices=fonts,
                        initial=str(current) if current is not None else None,
                    ),
                    after,
                )
            else:
                self.app.push_screen(
                    PromptModal(
                        title=f"Edit {setting.name}",
                        placeholder="font family name (fc-list not available)",
                        initial=str(current) if current is not None else "",
                        confirm_label="Apply",
                    ),
                    after,
                )
        else:
            initial_str = str(current) if current is not None else ""
            placeholder = (
                f"{setting.kind.value} (default: {setting.default})"
            )
            self.app.push_screen(
                PromptModal(
                    title=f"Edit {setting.name}",
                    placeholder=placeholder,
                    initial=initial_str,
                    confirm_label="Apply",
                ),
                after,
            )

    def action_reset(self) -> None:
        """Borra la entrada del archivo: el terminal usa su propio default."""
        option_list = self.query_one("#setting-list", OptionList)
        if option_list.highlighted is None:
            return
        setting = self.settings[option_list.highlighted]
        if self.backend.delete_setting(self.doc, setting):
            self.dirty = True
            self._refresh_header()
            self._rebuild_list()
            self.app.notify(
                f"{setting.name} reset (press 's' to save to disk)",
                severity="information",
                timeout=6,
            )
        else:
            self.app.notify(
                f"{setting.name} was already unset",
                severity="information",
            )

    def action_import(self) -> None:
        # Capability solo de Alacritty: import de settings desde otro
        # alacritty.toml. Mismo backend, no cross-backend.
        if not isinstance(self.backend, AlacrittyBackend):
            self.app.notify(
                f"Settings import not supported on {self.backend.display_name}.",
                severity="warning",
                timeout=6,
            )
            return
        backend = self.backend

        def after(path_str: str | None) -> None:
            if not path_str:
                return
            raw = Path(path_str).expanduser()
            path = raw if raw.is_absolute() else (self.backend_path.parent / raw)
            if not path.exists():
                self.app.notify(f"Does not exist: {path}", severity="error", timeout=8)
                return
            try:
                source = backend.load(path)
            except Exception as exc:  # noqa: BLE001
                self.app.notify(f"Load error: {exc}", severity="error", timeout=10)
                return
            count = 0
            for setting in self.settings:
                value = backend.read_setting(source, setting)
                if value is None:
                    continue
                try:
                    backend.write_setting(self.doc, setting, value)
                except ValueError:
                    continue
                count += 1
            if count == 0:
                self.app.notify(
                    "The file contains no recognized settings.",
                    severity="warning",
                    timeout=8,
                )
                return
            self.dirty = True
            self._refresh_header()
            self._rebuild_list()
            self.app.notify(
                f"Imported {count} setting(s) from {path.name}",
                severity="information",
                timeout=6,
            )

        self.app.push_screen(
            PromptModal(
                title="Import settings from file",
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
                # action_save hace notify de error y deja dirty=True si falla;
                # solo salimos si quedo limpio.
                self.action_save()
                if not self.dirty:
                    self.app.pop_screen()
                return
            # "cancel" o None: queda en el editor.

        self.app.push_screen(UnsavedChangesModal(), after)
