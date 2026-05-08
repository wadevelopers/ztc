from __future__ import annotations

import os
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from ztc import __version__
from ztc.models.config import Paths
from ztc.screens.color_editor import ColorEditorScreen
from ztc.screens.layout_list import LayoutListScreen
from ztc.screens.theme_editor import ThemePickerScreen
from ztc.sessions.screens.picker import PickerScreen
from ztc.sessions.services.zellij_session import attach_argv, new_session_argv
from ztc.sessions.types import LaunchTarget
from zellij_themes import theme_assets as zellij_theme_assets

from ztc.services import zellij_config, zellij_themes
from ztc.services.runtime_detect import (
    TerminalDetection,
    detect_terminal,
    detect_zellij_installed,
)
from ztc.services.terminals import TerminalBackend
from ztc.services.terminals.registry import (
    get_backend,
    is_backend_available,
)


_LOGO_ZTC = (
    "███████╗████████╗ ██████╗\n"
    "╚══███╔╝╚══██╔══╝██╔════╝\n"
    "  ███╔╝    ██║   ██║     \n"
    " ███╔╝     ██║   ██║     \n"
    "███████╗   ██║   ╚██████╗\n"
    "╚══════╝   ╚═╝    ╚═════╝"
)


class MenuOptionList(OptionList):
    """OptionList con los bindings de navegacion visibles en Footer.

    Reescribe los bindings que OptionList registra como `show=False`
    (`up`, `down`, `enter`) con `show=True` y `key_display` custom.
    Mantiene las mismas acciones (`cursor_up`/`cursor_down`/`select`)
    para no romper el comportamiento.
    """

    BINDINGS = [
        Binding("up", "cursor_up", "Navigate", key_display="↑↓", show=True),
        Binding("down", "cursor_down", "Navigate", show=False),
        Binding("enter", "select", "Open", key_display="↲", show=True),
    ]


class TermConfigApp(App[None]):
    TITLE = "ztc — Zellij & Terminal Config"
    SUB_TITLE = f"v{__version__}"

    # `ctrl+p` choca con el menu "pane" de Zellij; usamos `P` (Shift+P).
    # Binding propia para overridear el label "palette" que Textual hardcodea.
    COMMAND_PALETTE_BINDING = "P"
    BINDINGS = [
        Binding("P", "command_palette", "Palette", priority=True, show=False),
        Binding("q", "quit", "Exit"),
    ]

    DEFAULT_CSS = """
    #menu-wrap {
        padding: 1 2;
        align: center middle;
    }
    #logo {
        color: $secondary;
        text-style: bold;
        height: auto;
        text-align: center;
    }
    #logo-subtitle {
        color: $secondary;
        margin-bottom: 1;
        text-align: center;
    }
    #main-menu {
        height: auto;
        max-height: 20;
        width: 25;
        border: round $panel;
    }
    """

    def __init__(
        self,
        paths: Paths | None = None,
        backend: TerminalBackend | None = None,
        backend_path: Path | None = None,
        detection: TerminalDetection | None = None,
        zellij_installed: bool | None = None,
    ) -> None:
        super().__init__()
        self.paths = paths or Paths.default()
        self.detected_terminal = (
            detection if detection is not None else detect_terminal()
        )
        self.zellij_installed = (
            zellij_installed
            if zellij_installed is not None
            else detect_zellij_installed()
        )

        # Resolucion de backend:
        # - Si el caller pasa `backend` explicito (caso tests), se usa
        #   tal cual. Detection sigue corriendo y manda el menu, pero
        #   el backend lo controla el caller.
        # - Si no, se resuelve via registry segun deteccion. Si la
        #   terminal es no soportada o estamos por SSH, no hay backend.
        if backend is not None:
            self.backend: TerminalBackend | None = backend
            self.backend_path: Path | None = (
                backend_path or backend.default_config_path()
            )
        else:
            kind = self.detected_terminal.kind
            if is_backend_available(kind) and not self.detected_terminal.via_ssh:
                resolved = get_backend(kind)
                assert resolved is not None  # is_backend_available lo garantiza
                self.backend = resolved
                self.backend_path = (
                    backend_path or resolved.default_config_path()
                )
            else:
                self.backend = None
                self.backend_path = backend_path

    # ---------- compose / mount ----------

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="menu-wrap"):
            yield Static(_LOGO_ZTC, id="logo")
            yield Static("Zellij & Terminal Config", id="logo-subtitle")
            with Center():
                yield MenuOptionList(
                    *self._build_menu_options(),
                    id="main-menu",
                )
        yield Footer()

    def _build_menu_options(self) -> list[Option]:
        # Bloque "Tema/Layouts Zellij" depende solo de zellij_installed.
        zellij_suffix = "" if self.zellij_installed else "  (zellij not installed)"
        zellij_disabled = not self.zellij_installed

        # Bloque "Colores de terminal" depende del backend disponible y
        # de no estar por SSH; los dos bloques son independientes.
        colors_suffix, colors_disabled = self._colors_option_state()

        return [
            Option(
                f"Zellij theme{zellij_suffix}",
                id="themes",
                disabled=zellij_disabled,
            ),
            Option(
                f"Zellij layouts{zellij_suffix}",
                id="layouts",
                disabled=zellij_disabled,
            ),
            Option(
                f"Zellij sessions{zellij_suffix}",
                id="sessions",
                disabled=zellij_disabled,
            ),
            Option(
                f"Terminal colors{colors_suffix}",
                id="colors",
                disabled=colors_disabled,
            ),
        ]

    def _colors_option_state(self) -> tuple[str, bool]:
        d = self.detected_terminal
        if d.via_ssh:
            return "  (SSH)", True
        if d.invalid_override_value is not None:
            return "  (invalid override)", True
        if not is_backend_available(d.kind):
            return "  (unsupported)", True
        return "", False

    def on_mount(self) -> None:
        self._notify_detection()
        self.register_zellij_themes()
        self.sync_theme_with_zellij()
        self.query_one("#main-menu", OptionList).focus()

    def _notify_detection(self) -> None:
        d = self.detected_terminal

        if d.invalid_override_value is not None:
            self.notify(
                (
                    f"Invalid value for TERM_CONFIG_TUI_BACKEND: "
                    f"'{d.invalid_override_value}'. "
                    "Valid values: auto, alacritty, kitty."
                ),
                severity="warning",
                timeout=10,
            )
        elif d.via_ssh:
            self.notify(
                "You are over SSH; color editing does not apply to the client.",
                severity="warning",
                timeout=8,
            )
        elif not is_backend_available(d.kind):
            self.notify(
                (
                    "Terminal not supported for color editing. "
                    "Supported: Alacritty, Kitty."
                ),
                severity="warning",
                timeout=8,
            )

        if not self.zellij_installed:
            self.notify(
                "Zellij not installed: Zellij options disabled.",
                severity="warning",
                timeout=8,
            )

    # ---------- temas Textual sincronizados con Zellij ----------

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

    # ---------- handlers ----------

    @on(OptionList.OptionSelected, "#main-menu")
    def _on_menu_selected(self, event: OptionList.OptionSelected) -> None:
        # Guard defensivo: si la opcion esta disabled, OptionList no
        # deberia disparar este evento, pero por las dudas chequeamos.
        if event.option.disabled:
            return
        if event.option.id == "themes":
            self.push_screen(ThemePickerScreen(config_path=self.paths.zellij_config))
        elif event.option.id == "layouts":
            self.push_screen(LayoutListScreen(layouts_dir=self.paths.zellij_layouts_dir))
        elif event.option.id == "sessions":
            self.push_screen(
                PickerScreen(
                    on_launch=self._handle_session_launch,
                    on_cancel=self.pop_screen,
                )
            )
        elif event.option.id == "colors":
            if self.backend is None or self.backend_path is None:
                # No deberia pasar (la opcion estaria disabled), pero
                # defendemos contra inconsistencias.
                return
            self.push_screen(
                ColorEditorScreen(
                    backend=self.backend,
                    backend_path=self.backend_path,
                    zellij_config_path=self.paths.zellij_config,
                )
            )

    def _handle_session_launch(self, target: LaunchTarget) -> None:
        if target is None:
            return  # guard defensivo: cancel va por on_cancel, no deberia llegar acá.
        action, payload, extra = target
        if action == "attach":
            argv = attach_argv(payload or "")
        elif action == "new":
            argv = new_session_argv(payload or "", layout=extra)
        elif action == "bash":
            shell = os.environ.get("SHELL") or "/bin/bash"
            argv = [shell]
        else:
            return
        os.execvp(argv[0], argv)
