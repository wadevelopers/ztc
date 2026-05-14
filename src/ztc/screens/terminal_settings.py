"""Editor de settings de la terminal activa: padding, size, opacity, font,
cursor shape. Cubre los settings comunes con mapeo limpio entre
backends (Alacritty TOML y Kitty conf). Paralelo a `ColorEditorScreen`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from ztc.services.fonts import FontFace, list_monospace_fonts, resolve_font_faces
from ztc.services.profile_io import (
    expected_extension,
    resolve_profile_path,
    validate_profile_path,
)
from ztc.services.save_helper import compose_save_toast, save_profile_with_reload
from ztc.services.terminals import TerminalBackend
from ztc.services.terminals.settings import (
    CanonicalSetting,
    SettingKind,
    coerce_setting_value,
)
from ztc.widgets.confirm import (
    ConfirmActionModal,
    EnumPickerModal,
    FontPickerModal,
    PromptModal,
    UnsavedChangesModal,
)
from ztc.widgets.header import StaticHeader


class TerminalSettingsScreen(Screen[None]):
    """Editor de settings (no-color) del backend activo: padding, size,
    opacity, font size, font family, cursor shape.
    """

    BINDINGS = [
        Binding("enter", "edit", "Edit"),
        Binding("x", "reset", "Reset"),
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
        yield StaticHeader()
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
        if setting.name == "font.family" and isinstance(value, str):
            lines.extend(("", *self._font_faces_detail(value)))
        elif setting.name in ("window.padding.x", "window.padding.y"):
            lines.append("Unit: pixels")
        elif setting.name in ("window.columns", "window.lines"):
            lines.append("Unit: terminal cells")
            lines.extend(
                (
                    "",
                    "Note: For window size changes to take effect, restart your terminal.",
                )
            )
        meta_widget.update("\n".join(lines))

    def _font_faces_detail(self, family: str) -> list[str]:
        faces = resolve_font_faces(family)
        return [
            "Resolved faces:",
            f"normal: {self._format_font_face(faces.normal)}",
            f"bold: {self._format_font_face(faces.bold)}",
            f"italic: {self._format_font_face(faces.italic)}",
            f"bold_italic: {self._format_font_face(faces.bold_italic)}",
        ]

    @staticmethod
    def _format_font_face(face: FontFace) -> str:
        suffix = " (fallback)" if face.fallback else ""
        return f"{face.style}{suffix}"

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
            if not self.backend.is_managed_manifest(manifest_path):
                self._convert_then(
                    after_convert=lambda: self._do_load(path),
                    forbidden_path=path,
                    manifest_path=manifest_path,
                )
                return
            self._do_load(path)

        self.app.push_screen(
            PromptModal(
                title="Load profile from file",
                placeholder=f"filename (next to {manifest_path.name}) or absolute path",
                confirm_label="Load",
            ),
            after,
        )

    def _do_load(self, path: Path) -> None:
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
        self.app.notify(
            f"Loaded {path.name}", severity="information", timeout=6
        )

    def action_reload(self) -> None:
        self.doc = self.backend.load(self.backend_path)
        self.dirty = False
        self._refresh_header()
        self._rebuild_list()
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
        en Kitty el reload IPC lea las prefs runtime del manifest."""
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
        """Save-as a archivo nuevo. Si el default todavia no es manifest,
        dispara G2 conversion primero."""
        if not self.backend.is_managed_manifest(manifest_path):
            self._convert_then(
                after_convert=lambda: self._do_save_as(new_path),
                forbidden_path=None,
                manifest_path=manifest_path,
            )
            return
        self._do_save_as(new_path)

    def _do_save_as(self, new_path: Path) -> None:
        """Ejecuta save-as efectivo: write + set_active_profile. El reload
        lo dispara `set_active_profile`."""
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
        self.app.notify(
            f"Saved as {new_path.name}", severity="information", timeout=6
        )

    def _convert_then(
        self,
        *,
        after_convert: Callable[[], None],
        forbidden_path: Path | None,
        manifest_path: Path,
    ) -> None:
        """G2: pide nombre para el primer perfil (con los settings
        actuales del default), convierte, y dispara `after_convert`."""
        def after_name(name: str | None) -> None:
            if not name:
                return
            profile_path = resolve_profile_path(name, manifest_path.parent)
            error = validate_profile_path(
                self.backend,
                profile_path,
                manifest_path=manifest_path,
                forbidden_path=forbidden_path,
            )
            if error:
                self.app.notify(error, severity="error", timeout=8)
                return

            def do_convert() -> None:
                try:
                    self.backend.convert_to_manifest(manifest_path, profile_path)
                except Exception as exc:  # noqa: BLE001
                    self.app.notify(
                        f"Convert error: {exc}", severity="error", timeout=10
                    )
                    return
                after_convert()

            if profile_path.exists() and profile_path != manifest_path:
                def after_confirm(confirmed: bool | None) -> None:
                    if confirmed:
                        do_convert()
                self.app.push_screen(
                    ConfirmActionModal(
                        title="Overwrite file?",
                        message=f"{profile_path} already exists.",
                        confirm_label="Overwrite",
                    ),
                    after_confirm,
                )
                return
            do_convert()

        default_name = "default" + expected_extension(self.backend)
        self.app.push_screen(
            PromptModal(
                title="Convert to manifest",
                initial=default_name,
                placeholder="Name for current settings profile",
                confirm_label="Convert",
            ),
            after_name,
        )

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
                self._save_in_place(manifest_path)
                if not self.dirty:
                    self.app.pop_screen()
                return

        self.app.push_screen(UnsavedChangesModal(), after)
