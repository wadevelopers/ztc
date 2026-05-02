from __future__ import annotations

import subprocess
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from term_config_tui.models.session import ZellijSession
from term_config_tui.services import zellij_config, zellij_session
from term_config_tui.widgets.confirm import (
    ConfirmByNameModal,
    NewSessionModal,
    NewSessionResult,
)


class SessionManagerScreen(Screen[None]):
    """Pantalla para listar y administrar sesiones de Zellij."""

    BINDINGS = [
        Binding("enter", "attach", "Conectar"),
        Binding("n", "new", "Nueva"),
        Binding("l", "new_with_layout", "Nueva c/ layout"),
        Binding("k", "kill", "Cerrar"),
        Binding("x", "delete", "Borrar"),
        Binding("X", "delete_force", "Borrar --force"),
        Binding("r", "refresh", "Refrescar"),
        Binding("escape", "app.pop_screen", "Volver"),
        Binding("q", "app.pop_screen", "Volver", show=False),
    ]

    DEFAULT_CSS = """
    SessionManagerScreen {
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
    #detail-warn {
        color: $warning;
        margin-top: 1;
    }
    """

    def __init__(self, layouts_dir: Path) -> None:
        super().__init__()
        self.layouts_dir = layouts_dir
        self._sessions: list[ZellijSession] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="status")
        with Horizontal(id="body"):
            yield OptionList(id="session-list")
            with Vertical(id="detail"):
                yield Static("Selecciona una sesion.", id="detail-name")
                yield Static("", id="detail-meta")
                yield Static("", id="detail-warn")
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh()

    # ---------- carga / refresco ----------

    def action_refresh(self) -> None:
        self._sessions = zellij_session.list_sessions()
        option_list = self.query_one("#session-list", OptionList)
        option_list.clear_options()
        for s in self._sessions:
            option_list.add_option(Option(self._format_option(s), id=s.name))
        self._refresh_status()
        if self._sessions:
            option_list.highlighted = 0
            self._show_detail(self._sessions[0])
        else:
            self._show_detail(None)

    def _format_option(self, s: ZellijSession) -> str:
        marker = "* " if s.is_current else "  "
        state = f"[{s.state}]"
        return f"{marker}{s.name:<24} {state}"

    def _refresh_status(self) -> None:
        status = self.query_one("#status", Static)
        inside = zellij_session.is_inside_zellij()
        current = zellij_session.current_session_name() or "(ninguna)"
        env_part = f"dentro de zellij: {current}" if inside else "fuera de zellij"
        status.update(f"Sesiones: {len(self._sessions)}    {env_part}")

    def _show_detail(self, s: ZellijSession | None) -> None:
        name = self.query_one("#detail-name", Static)
        meta = self.query_one("#detail-meta", Static)
        warn = self.query_one("#detail-warn", Static)
        if s is None:
            name.update("Sin sesiones activas.")
            meta.update("")
            warn.update("Pulsa [b]n[/b] para crear una sesion nueva.")
            return
        name.update(s.name + ("  (esta sesion)" if s.is_current else ""))
        meta.update(f"Estado: {s.state}\n{s.raw_line or ''}")
        if s.is_current:
            warn.update("Cuidado: esta es la sesion donde corre este TUI.")
        elif s.state == "exited":
            warn.update(
                "Esta sesion esta resurrectable. [b]Enter[/b] la resucita con "
                "su layout original. [b]x[/b] la borra para siempre."
            )
        else:
            warn.update("")

    # ---------- helpers ----------

    def _highlighted_session(self) -> ZellijSession | None:
        option_list = self.query_one("#session-list", OptionList)
        if option_list.highlighted is None:
            return None
        opt = option_list.get_option_at_index(option_list.highlighted)
        return next((s for s in self._sessions if s.name == opt.id), None)

    @on(OptionList.OptionHighlighted, "#session-list")
    def _on_highlight(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is None:
            return
        s = next((x for x in self._sessions if x.name == event.option.id), None)
        if s is not None:
            self._show_detail(s)

    # ---------- acciones ----------

    def action_attach(self) -> None:
        s = self._highlighted_session()
        if s is None:
            return
        if zellij_session.is_inside_zellij():
            self.app.notify(
                "Ya estas dentro de zellij. Sal de la sesion actual antes de hacer attach.",
                severity="warning",
                timeout=8,
            )
            return
        if s.state == "exited":
            self.app.notify(
                f"Resucitando '{s.name}' con su layout original...",
                severity="information",
            )
        self._run_in_tty(zellij_session.attach_argv(s.name))
        self.action_refresh()

    def action_new(self) -> None:
        if zellij_session.is_inside_zellij():
            self.app.notify(
                "Ya estas dentro de zellij; no se puede crear otra sesion desde aqui.",
                severity="warning",
                timeout=8,
            )
            return
        self.app.push_screen(NewSessionModal(title="Nueva sesion"), self._after_new)

    def action_new_with_layout(self) -> None:
        if zellij_session.is_inside_zellij():
            self.app.notify(
                "Ya estas dentro de zellij; no se puede crear otra sesion desde aqui.",
                severity="warning",
                timeout=8,
            )
            return
        layouts = [layout.name for layout in zellij_config.list_layouts(self.layouts_dir)]
        self.app.push_screen(
            NewSessionModal(title="Nueva sesion con layout", layouts=layouts),
            self._after_new,
        )

    def _after_new(self, result: NewSessionResult | None) -> None:
        if result is None:
            return
        self._run_in_tty(
            zellij_session.new_session_argv(result.name, layout=result.layout)
        )
        self.action_refresh()

    def action_kill(self) -> None:
        s = self._highlighted_session()
        if s is None:
            return
        if s.is_current:
            self.app.notify(
                "No puedes matar la sesion donde corre este TUI.",
                severity="warning",
            )
            return
        self.app.push_screen(
            ConfirmByNameModal(
                title="Cerrar sesion viva",
                message=(
                    f"Esto cerrara la sesion \"{s.name}\" y todos los procesos dentro."
                ),
                expected=s.name,
                confirm_label="Cerrar",
            ),
            lambda ok: self._after_destructive(ok, s.name, action="kill"),
        )

    def action_delete(self) -> None:
        s = self._highlighted_session()
        if s is None:
            return
        self.app.push_screen(
            ConfirmByNameModal(
                title="Borrar sesion",
                message=(
                    f"Esto borrara la sesion \"{s.name}\". "
                    "Si esta viva fallara: usa Borrar --force."
                ),
                expected=s.name,
                confirm_label="Borrar",
            ),
            lambda ok: self._after_destructive(ok, s.name, action="delete"),
        )

    def action_delete_force(self) -> None:
        s = self._highlighted_session()
        if s is None:
            return
        if s.is_current:
            self.app.notify(
                "No puedes borrar la sesion donde corre este TUI.",
                severity="warning",
            )
            return
        self.app.push_screen(
            ConfirmByNameModal(
                title="Borrar sesion --force",
                message=(
                    f"Esto matara y borrara \"{s.name}\" sin importar su estado. "
                    "Los procesos dentro se cerraran."
                ),
                expected=s.name,
                confirm_label="Borrar --force",
            ),
            lambda ok: self._after_destructive(ok, s.name, action="delete-force"),
        )

    def _after_destructive(self, ok: bool, name: str, *, action: str) -> None:
        if not ok:
            self.app.notify("Cancelado.", severity="information")
            return
        if action == "kill":
            ok2, out = zellij_session.kill_session(name)
        elif action == "delete":
            ok2, out = zellij_session.delete_session(name)
        elif action == "delete-force":
            ok2, out = zellij_session.delete_session(name, force=True)
        else:  # pragma: no cover
            return
        if ok2:
            self.app.notify(f"OK: {action} {name}", severity="information")
        else:
            self.app.notify(
                f"Fallo {action} {name}: {out or 'sin output'}",
                severity="error",
                timeout=10,
            )
        self.action_refresh()

    def _run_in_tty(self, argv: list[str]) -> None:
        """Suspende el TUI, libera la TTY para correr argv, y restaura al volver."""
        try:
            with self.app.suspend():
                subprocess.run(argv, check=False)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Error ejecutando {argv[0]}: {exc}", severity="error")
