from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from ztc.sessions.models.session import ZellijSession
from ztc.sessions.services import layouts as layouts_svc
from ztc.sessions.services import session_info, state, zellij_session
from ztc.sessions.services.session_info import PaneInfo, TabInfo
from ztc.sessions.types import LaunchTarget
from ztc.sessions.widgets.modals import (
    ConfirmByNameModal,
    NewSessionModal,
    NewSessionResult,
)


class PickerScreen(Screen[None]):
    """Pantalla principal: lista de sesiones a la izquierda, detalles a la derecha."""

    BINDINGS = [
        Binding("enter", "attach", "Attach"),
        Binding("n", "new_session", "New"),
        Binding("l", "new_with_layout", "New +layout"),
        Binding("r", "rename", "Rename"),
        Binding("k", "kill", "Kill"),
        Binding("d", "delete", "Delete"),
        Binding("D", "delete_force", "--force"),
        Binding("b", "bash", "Bash"),
        Binding("R", "refresh", "Refresh"),
        Binding("q", "quit", "Exit"),
        Binding("escape", "quit", "Exit", show=False),
    ]

    DEFAULT_CSS = """
    PickerScreen {
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
    #detail {
        padding: 1 2;
        height: 1fr;
    }
    #detail-name {
        text-style: bold;
        color: $accent;
    }
    #detail-meta, #detail-tabs, #detail-extra {
        margin-top: 1;
    }
    #empty-hint {
        padding: 1 2;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        *,
        on_launch: Callable[[LaunchTarget], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        zellij_installed: bool = True,
        embedded: bool = False,
    ) -> None:
        super().__init__()
        self._sessions: list[ZellijSession] = []
        self._on_launch = on_launch or self._default_launch
        self._on_cancel = on_cancel or self._default_cancel
        self._zellij_installed = zellij_installed
        self._embedded = embedded
        if embedded:
            # En modo embebido, "cancel" vuelve al menu (no cierra la app).
            # Ocultamos `q Exit` del Footer y mostramos `Esc Back` para
            # reflejar la accion real. La tecla `q` sigue funcionando como
            # atajo (no se anuncia, pero llama a action_quit -> on_cancel).
            self._bindings.key_to_bindings["q"] = [
                Binding("q", "quit", "Back", show=False)
            ]
            self._bindings.key_to_bindings["escape"] = [
                Binding("escape", "quit", "Back", show=True)
            ]

    def _require_zellij(self) -> bool:
        """Guard: si zellij no esta instalado, notifica y devuelve False.
        Las acciones que requieren `zellij` (attach/new/new+layout/bash)
        lo llaman al inicio y abortan si retorna False."""
        if self._zellij_installed:
            return True
        self.app.notify(
            "Zellij is not installed. Install it first.",
            severity="error",
            timeout=4,
        )
        return False

    def _default_launch(self, target: LaunchTarget) -> None:
        # Comportamiento standalone: setear target en la app + exit;
        # __main__ lee target y hace os.execvp.
        self.app.target = target  # type: ignore[attr-defined]
        self.app.exit()

    def _default_cancel(self) -> None:
        # Comportamiento standalone: target=None + exit.
        self.app.target = None  # type: ignore[attr-defined]
        self.app.exit()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="status")
        with Horizontal(id="body"):
            yield OptionList(id="session-list")
            with Vertical(id="detail"):
                yield Static("", id="detail-name")
                yield Static("", id="detail-meta")
                yield Static("", id="detail-tabs")
                yield Static("", id="detail-extra")
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh()

    # ---------- listado y detalles ----------

    def action_refresh(self) -> None:
        self._sessions = zellij_session.list_sessions()
        option_list = self.query_one("#session-list", OptionList)
        option_list.clear_options()
        for s in self._sessions:
            option_list.add_option(Option(self._format_row(s), id=s.name))
        self._refresh_status()
        if self._sessions:
            option_list.highlighted = 0
            self._show_detail(self._sessions[0])
        else:
            self._show_detail(None)

    # Colores por estado:
    # - attached: verde (server vivo + cliente conectado)
    # - detached: amarillo (server vivo, terminal cerrada sin salir)
    # - exited:   rojo (server muerto, resurrectable)
    # - running:  default (fallback si la deteccion de clientes no anda)
    # - unknown:  gris
    _STATE_COLORS: dict[str, str] = {
        "attached": "green",
        "detached": "yellow",
        "exited": "red",
        "running": "white",
        "unknown": "dim",
    }

    # Anchos de columna del listado: nombre fijo a 24, estado a 10.
    _NAME_COL = 24
    _STATE_COL = 10

    def _state_label(self, s: ZellijSession) -> str:
        if s.state == "attached" and s.attached_clients > 1:
            return f"{s.state} ({s.attached_clients})"
        return s.state

    def _format_row(self, s: ZellijSession) -> Text:
        """Construye una fila tipo `<nombre>  <estado>` con el estado
        coloreado. Usa Text en lugar de string-con-markup para evitar
        que los brackets/parentesis del estado se interpreten como tags."""
        text = Text()
        text.append(f"{s.name:<{self._NAME_COL}}  ")
        text.append(
            f"{self._state_label(s):<{self._STATE_COL}}",
            style=self._STATE_COLORS.get(s.state, "white"),
        )
        return text

    def _refresh_status(self) -> None:
        status = self.query_one("#status", Static)
        n = len(self._sessions)
        if n == 0:
            status.update("No sessions. Press [b]n[/b] or [b]l[/b] to create, [b]b[/b] for bash.")
        else:
            status.update(f"{n} session(s) — Enter attaches/resurrects the highlighted one.")

    def _show_detail(self, s: ZellijSession | None) -> None:
        name_w = self.query_one("#detail-name", Static)
        meta_w = self.query_one("#detail-meta", Static)
        tabs_w = self.query_one("#detail-tabs", Static)
        extra_w = self.query_one("#detail-extra", Static)

        if s is None:
            name_w.update("No session selected.")
            meta_w.update(
                "Create one with [b]n[/b] (default: 'main') or with layout: [b]l[/b].\n"
                "Launch bash without Zellij with [b]b[/b]."
            )
            tabs_w.update("")
            extra_w.update("")
            return

        details = session_info.read_session_details(s.name)
        name_w.update(s.name)
        color = self._STATE_COLORS.get(s.state, "white")
        state_label = s.state
        if s.state == "attached" and s.attached_clients > 1:
            state_label = f"{state_label} ({s.attached_clients} clients)"
        meta_lines = [f"Status: [{color}]{state_label}[/]"]
        if details and details.mtime:
            meta_lines.append(
                f"Last activity: {datetime.fromtimestamp(details.mtime):%Y-%m-%d %H:%M}"
            )
        meta_w.update("\n".join(meta_lines))

        # Tabs + panes (arbol indentado).
        if details and details.tabs:
            tabs_w.update(self._render_tabs_tree(details.tabs))
        else:
            tabs_w.update("")

        extra_w.update("")

    def _render_tabs_tree(self, tabs: list[TabInfo]) -> str:
        """Devuelve un texto multilinea con cada tab y sus paneles en
        un arbol con caracteres `├─/└─/│`. Tabs sin paneles utiles
        muestran `(sin comandos)`."""
        lines: list[str] = []
        for tab in tabs:
            lines.append(f"[b]{tab.name}[/]")
            # En zellij, los panes top-level dentro de un tab apilan
            # por default en filas (split horizontal del tab). Lo
            # pasamos como parent_direction para que la inferencia
            # del opuesto funcione en el primer nivel.
            pane_lines = self._render_panes(
                tab.panes, prefix="", parent_direction="horizontal"
            )
            if pane_lines:
                lines.extend(pane_lines)
            else:
                lines.append("  [dim](no commands)[/]")
            lines.append("")  # separador entre tabs
        if lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

    def _render_panes(
        self,
        panes: list[PaneInfo],
        *,
        prefix: str,
        parent_direction: str | None,
    ) -> list[str]:
        """Renderea panes como arbol. `prefix` es el string que precede
        al conector. `parent_direction` es el split_direction del
        container que contiene `panes`; sirve para inferir la dirección
        de containers que no la declaran explícitamente (zellij usa el
        opuesto del padre como default).

        Detecta auto-equiparticion: si todos los hermanos del grupo
        tienen el mismo `size`, asumimos que Zellij lo computo
        automaticamente al cargar el layout (no es eleccion del
        usuario) y ocultamos el size al renderear."""
        out: list[str] = []
        hide_sizes = self._is_auto_distribution(panes)
        for i, p in enumerate(panes):
            is_last = i == len(panes) - 1
            connector = "└─ " if is_last else "├─ "
            # Dirección efectiva: lo declarado, o si no, el opuesto
            # de la dirección del padre (regla de zellij).
            effective_direction = (
                p.split_direction or self._opposite_direction(parent_direction)
            )
            out.append(
                self._format_pane_line(
                    p,
                    line_prefix=prefix + connector,
                    hide_size=hide_sizes,
                    effective_direction=effective_direction,
                )
            )
            # Para los hijos: si yo soy ultimo, el espacio bajo mi
            # rama es vacio; si no, mantengo `│` para mostrar la
            # continuacion vertical.
            child_prefix = prefix + ("   " if is_last else "│  ")
            out.extend(
                self._render_panes(
                    p.children,
                    prefix=child_prefix,
                    parent_direction=effective_direction,
                )
            )
        return out

    @staticmethod
    def _opposite_direction(direction: str | None) -> str | None:
        if direction == "horizontal":
            return "vertical"
        if direction == "vertical":
            return "horizontal"
        return None

    @staticmethod
    def _is_auto_distribution(panes: list[PaneInfo]) -> bool:
        """True si todos los panes tienen el mismo size — firma de
        equiparticion automatica de Zellij sobre panes sin size
        explicito en el KDL del usuario. En ese caso ocultamos el
        size porque no representa intent del usuario."""
        if len(panes) <= 1:
            return False
        sizes = {p.size for p in panes}
        return len(sizes) == 1 and None not in sizes

    def _format_pane_line(
        self,
        pane: PaneInfo,
        *,
        line_prefix: str,
        hide_size: bool = False,
        effective_direction: str | None = None,
    ) -> str:
        """Devuelve la linea para un pane.

        Containers (panes con children) son agrupadores estructurales,
        no terminales reales: muestran solo `[rows · 60%]`, `[columns]`
        o similar — sin cwd, swatch ni cmd. La dirección viene de
        `effective_direction` (declarada o inferida del padre).

        Leaves (panes sin children) muestran un bloque de 4 chars con
        el bg color y el size adentro, seguido del cmd + cwd."""
        is_container = bool(pane.children)
        if is_container:
            head = self._direction_label(effective_direction) or "container"
            parts = [head]
            if pane.size and not hide_size:
                parts.append(pane.size)
            # `\[` escapa el bracket para que Rich no lo interprete como tag.
            label = "\\[" + " · ".join(parts) + "]"
            return f"{line_prefix}[dim]{label}[/]"

        swatch = self._bg_swatch(
            pane.default_bg, pane.size if not hide_size else None
        )
        body = self._pane_body(pane)
        return f"{line_prefix}{swatch}{body}"

    def _pane_body(self, pane: PaneInfo) -> str:
        """Texto del pane sin swatch ni size (esos viven adentro del
        swatch). Formato: `[<cmd>  ]<cwd>` o `(sin info)`."""
        if pane.command:
            cwd_part = (
                f"  [dim]{self._collapse_home(pane.cwd)}[/]" if pane.cwd else ""
            )
            return f"{pane.command}{cwd_part}"
        if pane.cwd:
            return self._collapse_home(pane.cwd)
        return "[dim](no info)[/]"

    # Color de fallback cuando un pane no declara `default_bg`. Tiene
    # que ser visible contra el bg del panel del TUI (asumimos dark
    # theme; en light theme podria leerse raro pero es minoritario).
    _NEUTRAL_SWATCH_BG = "#3a3a3a"

    @classmethod
    def _bg_swatch(cls, bg: str | None, size: str | None) -> str:
        """Bloque de 4 chars con bg color y size adentro (right-aligned).
        Si el pane no tiene `default_bg`, usa un gris neutral.
        El foreground del texto se elige segun la luminancia del bg
        para que el size siempre sea legible."""
        bg_color = bg if bg else cls._NEUTRAL_SWATCH_BG
        fg_color = cls._contrast_text_color(bg_color)
        label = (size or "").rjust(4)[:4]
        return f"[{fg_color} on {bg_color}]{label}[/] "

    @staticmethod
    def _contrast_text_color(bg_hex: str) -> str:
        """Negro o blanco segun la luminancia percibida del bg.
        Usa la formula estandar (0.299*r + 0.587*g + 0.114*b)."""
        try:
            r = int(bg_hex[1:3], 16)
            g = int(bg_hex[3:5], 16)
            b = int(bg_hex[5:7], 16)
        except (ValueError, IndexError):
            return "white"
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return "black" if luminance > 0.55 else "white"

    @staticmethod
    def _direction_label(split_direction: str | None) -> str | None:
        """Mapea `split_direction` del KDL a etiqueta corta.
        Convencion de Zellij: `horizontal` apila los children en filas
        (divisor horizontal entre filas), `vertical` los pone en
        columnas (divisor vertical entre columnas)."""
        if split_direction == "horizontal":
            return "rows"
        if split_direction == "vertical":
            return "columns"
        return None

    @staticmethod
    def _collapse_home(path: str) -> str:
        """Reemplaza el home del usuario por `~` para acortar paths."""
        home = str(Path.home())
        if path == home:
            return "~"
        if path.startswith(home + "/"):
            return "~" + path[len(home):]
        return path

    @on(OptionList.OptionHighlighted, "#session-list")
    def _on_highlight(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is None:
            return
        s = next((x for x in self._sessions if x.name == event.option.id), None)
        if s is not None:
            self._show_detail(s)

    @on(OptionList.OptionSelected, "#session-list")
    def _on_select(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is not None:
            self.action_attach()

    # ---------- helpers ----------

    def _highlighted(self) -> ZellijSession | None:
        option_list = self.query_one("#session-list", OptionList)
        if option_list.highlighted is None or not self._sessions:
            return None
        opt = option_list.get_option_at_index(option_list.highlighted)
        return next((s for s in self._sessions if s.name == opt.id), None)

    def _existing_names(self) -> set[str]:
        return {s.name for s in self._sessions}

    # ---------- acciones que ejecutan zellij/bash (exec) ----------

    def action_attach(self) -> None:
        if not self._require_zellij():
            return
        s = self._highlighted()
        if s is None:
            return
        self._on_launch(("attach", s.name, None))

    def action_bash(self) -> None:
        # bash no requiere zellij — funciona sin zellij instalado.
        self._on_launch(("bash", None, None))

    def action_new_session(self) -> None:
        if not self._require_zellij():
            return
        default = zellij_session.next_default_name(self._existing_names())
        self.app.push_screen(
            NewSessionModal(title="New session", default_name=default),
            self._after_new,
        )

    def action_new_with_layout(self) -> None:
        if not self._require_zellij():
            return
        default_name = zellij_session.next_default_name(self._existing_names())
        layouts = layouts_svc.list_layout_files()
        if not layouts:
            self.app.notify(
                "No layouts found in ~/.config/zellij/layouts/.",
                severity="warning",
                timeout=6,
            )
            return
        default_layout = (
            state.get_last_layout()
            or layouts_svc.zellij_default_layout()
            or layouts[0]
        )
        self.app.push_screen(
            NewSessionModal(
                title="New session with layout",
                default_name=default_name,
                layouts=layouts,
                default_layout=default_layout,
            ),
            self._after_new,
        )

    def _after_new(self, result: NewSessionResult | None) -> None:
        if result is None:
            return
        if result.layout:
            state.set_last_layout(result.layout)
        self._on_launch(("new", result.name, result.layout))

    # ---------- acciones in-place (no salen del TUI) ----------

    def action_rename(self) -> None:
        s = self._highlighted()
        if s is None:
            return
        # Zellij does not support rename-session on exited sessions.
        if s.state == "exited":
            self.app.notify(
                f"Cannot rename '{s.name}': the session is exited. "
                "Resurrect it first (Enter) and try again.",
                severity="warning",
                timeout=8,
            )
            return
        existing = self._existing_names() - {s.name}

        def after(result: NewSessionResult | None) -> None:
            if result is None:
                return
            new_name = result.name
            if new_name == s.name:
                return
            if new_name in existing:
                self.app.notify(
                    f"Session '{new_name}' already exists.",
                    severity="error",
                    timeout=6,
                )
                return
            success, out = zellij_session.rename_session(s.name, new_name)
            if not success:
                msg = f"Could not rename '{s.name}': {out or 'unknown failure'}"
                self.app.notify(msg, severity="error", timeout=10)
                return
            self.app.notify(
                f"'{s.name}' → '{new_name}'",
                severity="information",
                timeout=6,
            )
            self.action_refresh()

        self.app.push_screen(
            NewSessionModal(
                title=f"Rename session '{s.name}'",
                default_name=s.name,
                confirm_label="Rename",
            ),
            after,
        )

    def action_kill(self) -> None:
        s = self._highlighted()
        if s is None:
            return
        self.app.push_screen(
            ConfirmByNameModal(
                title="Kill session",
                message=(
                    f"This will kill the session \"{s.name}\" and all its processes."
                ),
                expected=s.name,
                confirm_label="Kill",
            ),
            lambda ok: self._after_destructive(ok, s.name, "kill"),
        )

    def action_delete(self) -> None:
        s = self._highlighted()
        if s is None:
            return
        self.app.push_screen(
            ConfirmByNameModal(
                title="Delete session",
                message=(
                    f"Deletes the cache of \"{s.name}\". If the session is alive it will fail: "
                    "use Delete --force."
                ),
                expected=s.name,
                confirm_label="Delete",
            ),
            lambda ok: self._after_destructive(ok, s.name, "delete"),
        )

    def action_delete_force(self) -> None:
        s = self._highlighted()
        if s is None:
            return
        self.app.push_screen(
            ConfirmByNameModal(
                title="Delete session --force",
                message=(
                    f"Kills AND deletes \"{s.name}\". Processes inside die. "
                    "Not reversible."
                ),
                expected=s.name,
                confirm_label="Delete --force",
            ),
            lambda ok: self._after_destructive(ok, s.name, "delete-force"),
        )

    def _after_destructive(self, ok: bool, name: str, action: str) -> None:
        if not ok:
            self.app.notify("Cancelled.", severity="information")
            return
        if action == "kill":
            success, out = zellij_session.kill_session(name)
        elif action == "delete":
            success, out = zellij_session.delete_session(name)
        elif action == "delete-force":
            success, out = zellij_session.delete_session(name, force=True)
        else:
            return
        severity = "information" if success else "error"
        msg = f"{action} {name}: {'OK' if success else 'failed'}"
        if out and not success:
            msg += f" — {out}"
        self.app.notify(msg, severity=severity, timeout=8)
        self.action_refresh()

    def action_quit(self) -> None:
        self._on_cancel()
