from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from ztc import __version__
from ztc.models.config import Paths
from ztc.screens.color_editor import ColorEditorScreen
from ztc.screens.layout_list import LayoutListScreen
from ztc.screens.terminal_settings import TerminalSettingsScreen
from ztc.screens.theme_editor import ThemePickerScreen
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
from ztc.sessions.screens.picker import PickerScreen
from ztc.sessions.types import LaunchTarget
from ztc.startup_checks import build_startup_check
from ztc.widgets.confirm import BUTTON_CSS
from ztc.widgets.header import StaticHeader
from ztc.zellij import TEXTUAL_FALLBACK
from ztc.zellij import theme_assets as zellij_theme_assets
from ztc.zellij.config import read_active_theme
from ztc.zellij.user_themes import list_user_themes

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
    #company-link {
        color: $text-muted;
        margin-top: 1;
        text-align: center;
    }
    #main-menu {
        height: auto;
        max-height: 20;
        border: round $panel;
    }
    /* Sin suffixes: ancho compacto (igual al logo). */
    #main-menu.narrow {
        width: 25;
    }
    /* Con suffixes "(zellij not installed)" / "(unsupported)" / etc.:
       ancho amplio para que los suffixes quepan alineados a la derecha. */
    #main-menu.wide {
        width: 43;
    }
    """ + BUTTON_CSS

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

        # Target diferido del launcher embebido. Si el usuario elige
        # attach/new/bash desde "Zellij sessions", lo guardamos aca y
        # llamamos `self.exit()`. El `execvp` lo hace `__main__.py`
        # despues que Textual restaura el estado de la terminal — sin
        # eso, zellij hereda raw mode + alt-screen y la terminal queda
        # bloqueada al salir.
        self.pending_launch: LaunchTarget = None

    # ---------- compose / mount ----------

    def compose(self) -> ComposeResult:
        yield StaticHeader()
        with Vertical(id="menu-wrap"):
            yield Static(_LOGO_ZTC, id="logo")
            yield Static("Zellij & Terminal Config", id="logo-subtitle")
            with Center():
                yield MenuOptionList(
                    *self._build_menu_options(),
                    id="main-menu",
                    classes="wide" if self._has_menu_suffixes() else "narrow",
                )
            yield Static(self._company_link(), id="company-link")
        yield Footer()

    # Ancho util de contenido del menu en modo "wide" (width 43). Verificado
    # en runtime: el OptionList expone content_size.width=39 cuando el widget
    # mide 43 (border + padding/scroll-reserve consumen 4 cells, no 2).
    _MENU_WIDE_INNER = 39

    @staticmethod
    def _company_link() -> Text:
        """Texto con la URL como hyperlink ANSI (OSC 8). Lo construimos
        con Text + style en vez de markup `[link=URL]` porque el parser
        de Rich markup interpreta mal el `://` de URLs sin comillas."""
        text = Text()
        text.append("WA Developers SRL — ", style="dim")
        text.append(
            "wadevelopers.com",
            style="underline link https://wadevelopers.com",
        )
        return text

    def _has_menu_suffixes(self) -> bool:
        """True si algun item del menu tendria suffix (zellij not installed,
        SSH, unsupported, invalid override). Define si el menu se renderiza
        narrow (25, igual al logo) o wide (43, suffixes alineados a derecha)."""
        if not self.zellij_installed:
            return True
        colors_suffix, _ = self._colors_option_state()
        return bool(colors_suffix)

    def _build_menu_options(self) -> list[Option]:
        # Bloque "Tema/Layouts/Sessions Zellij" depende solo de zellij_installed.
        zellij_suffix = "" if self.zellij_installed else "  (zellij not installed)"
        zellij_disabled = not self.zellij_installed

        # Bloque "Colores de terminal" depende del backend disponible y
        # de no estar por SSH; los dos bloques son independientes.
        colors_suffix, colors_disabled = self._colors_option_state()

        # Si hay suffixes, padear cada label para que el suffix quede pegado
        # al borde derecho del menu. ljust al ancho disponible menos el largo
        # del suffix, asi el suffix llena hasta el final.
        def _padded(label: str, suffix: str) -> str:
            if not suffix:
                return label
            return label.ljust(self._MENU_WIDE_INNER - len(suffix)) + suffix

        return [
            Option(
                _padded("Zellij themes", zellij_suffix),
                id="themes",
                disabled=zellij_disabled,
            ),
            Option(
                _padded("Zellij layouts", zellij_suffix),
                id="layouts",
                disabled=zellij_disabled,
            ),
            Option(
                _padded("Zellij sessions", zellij_suffix),
                id="sessions",
                disabled=zellij_disabled,
            ),
            Option(
                _padded("Terminal colors", colors_suffix),
                id="colors",
                disabled=colors_disabled,
            ),
            Option(
                _padded("Terminal settings", colors_suffix),
                id="terminal-settings",
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
        if self.backend is not None and self.backend_path is not None:
            check = build_startup_check(self.backend, self.backend_path, self)
            if check is not None:
                self.push_screen(check.modal, check.on_result)

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
                "Terminal not supported\nSupported: Alacritty, Kitty",
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
        for ut in list_user_themes(self.paths.zellij_config):
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
        active = read_active_theme(self.paths.zellij_config)
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
        target = zellij_name if zellij_name else TEXTUAL_FALLBACK
        if target not in self.available_themes:
            target = TEXTUAL_FALLBACK
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
                    zellij_installed=self.zellij_installed,
                    embedded=True,
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
        elif event.option.id == "terminal-settings":
            if self.backend is None or self.backend_path is None:
                return
            self.push_screen(
                TerminalSettingsScreen(
                    backend=self.backend,
                    backend_path=self.backend_path,
                )
            )

    def _handle_session_launch(self, target: LaunchTarget) -> None:
        if target is None:
            return  # guard defensivo: cancel va por on_cancel, no deberia llegar acá.
        # No `execvp` directo aca: estamos dentro del event loop de Textual,
        # con la terminal en raw mode + alt-screen. Si reemplazamos el
        # proceso ahora, zellij hereda ese estado y al salir la terminal
        # queda bloqueada. En su lugar, guardamos el target y salimos
        # limpiamente; `__main__.py` ejecuta `execvp` despues que Textual
        # restauro la terminal.
        self.pending_launch = target
        self.exit()
