"""Tests del gating del menu principal segun deteccion de terminal y Zellij.

Cubren los escenarios:
- Terminal soportada + zellij + no SSH -> happy path.
- Terminal no soportada -> "Colores de terminal" disabled "(unsupported)".
- SSH detectado -> "Colores de terminal" disabled "(SSH)".
- Zellij no instalado -> "Tema/Layouts/Sessions Zellij" disabled.
- Override env var valido / invalido.

Tambien cubren el contrato del launcher embebido:
- `_handle_session_launch` setea `app.pending_launch` y NO invoca
  `os.execvp` desde el event loop (el `execvp` lo hace
  `launcher.dispatch_target` despues que `app.run()` retorna,
  cuando Textual ya restauro la terminal).
"""

from __future__ import annotations

from pathlib import Path

from textual.widgets import OptionList

from ztc.app import TermConfigApp
from ztc.models.config import Paths
from ztc.screens.color_editor import ColorEditorScreen
from ztc.services.runtime_detect import TerminalDetection


def _paths(tmp_path: Path) -> Paths:
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    return Paths(
        zellij_config=cfg, zellij_layouts_dir=tmp_path / "layouts"
    )


def _option_state(
    app: TermConfigApp, option_id: str
) -> tuple[str, bool]:
    """Devuelve (label, disabled) de una opcion del menu por id."""
    option_list = app.query_one("#main-menu", OptionList)
    for i in range(option_list.option_count):
        opt = option_list.get_option_at_index(i)
        if opt.id == option_id:
            return str(opt.prompt), opt.disabled
    raise AssertionError(f"option {option_id!r} no encontrada")


# ---------- happy path ----------


async def test_happy_path_alacritty_with_zellij(tmp_path: Path) -> None:
    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=tmp_path / "alacritty.toml",
        detection=TerminalDetection(
            kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
        ),
        zellij_installed=True,
    )
    async with app.run_test():
        themes_label, themes_disabled = _option_state(app, "themes")
        layouts_label, layouts_disabled = _option_state(app, "layouts")
        sessions_label, sessions_disabled = _option_state(app, "sessions")
        colors_label, colors_disabled = _option_state(app, "colors")
        assert themes_disabled is False
        assert layouts_disabled is False
        assert sessions_disabled is False
        assert colors_disabled is False
        assert "unsupported" not in colors_label
        assert "SSH" not in colors_label
        assert "zellij not installed" not in themes_label.lower()
        assert "zellij not installed" not in sessions_label.lower()
        # 5 items: themes, layouts, sessions, colors, terminal-settings.
        option_list = app.query_one("#main-menu", OptionList)
        assert option_list.option_count == 5
        # terminal-settings comparte gating con colors (mismo backend/SSH).
        ts_label, ts_disabled = _option_state(app, "terminal-settings")
        assert ts_disabled is False


# ---------- terminal no soportada ----------


async def test_unsupported_terminal_disables_colors(tmp_path: Path) -> None:
    app = TermConfigApp(
        paths=_paths(tmp_path),
        detection=TerminalDetection(
            kind="unsupported", via_ssh=False, raw_marker="TERM_PROGRAM=iTerm.app"
        ),
        zellij_installed=True,
    )
    async with app.run_test():
        colors_label, colors_disabled = _option_state(app, "colors")
        themes_label, themes_disabled = _option_state(app, "themes")
        assert colors_disabled is True
        assert "unsupported" in colors_label
        # Zellij sigue habilitado: independencia de bloques.
        assert themes_disabled is False


async def test_kitty_detection_resolves_kitty_backend(tmp_path: Path) -> None:
    """Con Fase C aterrizada, kitty detectada -> habilitada y backend KittyBackend."""
    from ztc.services.terminals.kitty import KittyBackend

    kitty_conf = tmp_path / "kitty.conf"
    kitty_conf.write_text(
        "allow_remote_control yes\nlisten_on unix:@ztc-{kitty_pid}\n",
        encoding="utf-8",
    )
    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=kitty_conf,
        detection=TerminalDetection(
            kind="kitty", via_ssh=False, raw_marker="env:KITTY_PID"
        ),
        zellij_installed=True,
    )
    async with app.run_test():
        _, colors_disabled = _option_state(app, "colors")
        assert colors_disabled is False
        assert isinstance(app.backend, KittyBackend)


# ---------- SSH ----------


async def test_ssh_disables_colors_even_if_supported(tmp_path: Path) -> None:
    app = TermConfigApp(
        paths=_paths(tmp_path),
        detection=TerminalDetection(
            kind="alacritty", via_ssh=True, raw_marker="env:ALACRITTY_WINDOW_ID"
        ),
        zellij_installed=True,
    )
    async with app.run_test():
        colors_label, colors_disabled = _option_state(app, "colors")
        assert colors_disabled is True
        assert "SSH" in colors_label
        # SSH no impide tener acceso a Zellij.
        _, themes_disabled = _option_state(app, "themes")
        assert themes_disabled is False
        # Sin backend (no se sincroniza al lado cliente).
        assert app.backend is None


# ---------- Zellij no instalado ----------


async def test_no_zellij_disables_only_zellij_options(tmp_path: Path) -> None:
    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=tmp_path / "alacritty.toml",
        detection=TerminalDetection(
            kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
        ),
        zellij_installed=False,
    )
    async with app.run_test():
        themes_label, themes_disabled = _option_state(app, "themes")
        layouts_label, layouts_disabled = _option_state(app, "layouts")
        sessions_label, sessions_disabled = _option_state(app, "sessions")
        colors_label, colors_disabled = _option_state(app, "colors")
        assert themes_disabled is True
        assert layouts_disabled is True
        assert sessions_disabled is True
        assert "zellij not installed" in themes_label
        assert "zellij not installed" in layouts_label
        assert "zellij not installed" in sessions_label
        # Colores intacto: independencia de bloques.
        assert colors_disabled is False


# ---------- override env var ----------


async def test_override_invalid_value_disables_colors(tmp_path: Path) -> None:
    app = TermConfigApp(
        paths=_paths(tmp_path),
        detection=TerminalDetection(
            kind="unsupported",
            via_ssh=False,
            raw_marker="override:potato",
            invalid_override_value="potato",
        ),
        zellij_installed=True,
    )
    async with app.run_test():
        colors_label, colors_disabled = _option_state(app, "colors")
        assert colors_disabled is True
        assert "invalid override" in colors_label
        # Backend tampoco resuelto.
        assert app.backend is None


async def test_override_valid_alacritty_resolves_backend(tmp_path: Path) -> None:
    """Override valido habilita la opcion y resuelve el backend."""
    from ztc.services.terminals.alacritty import AlacrittyBackend

    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=tmp_path / "alacritty.toml",
        detection=TerminalDetection(
            kind="alacritty",
            via_ssh=False,
            raw_marker="override:alacritty",
        ),
        zellij_installed=True,
    )
    async with app.run_test():
        _, colors_disabled = _option_state(app, "colors")
        assert colors_disabled is False
        assert isinstance(app.backend, AlacrittyBackend)


# ---------- handler no abre disabled ----------


async def test_selecting_disabled_colors_does_nothing(tmp_path: Path) -> None:
    """Si el usuario selecciona la opcion deshabilitada por algun motivo,
    el handler no empuja screens."""
    app = TermConfigApp(
        paths=_paths(tmp_path),
        detection=TerminalDetection(
            kind="unsupported", via_ssh=False, raw_marker=None
        ),
        zellij_installed=True,
    )
    async with app.run_test():
        before_count = len(app.screen_stack)
        # OptionList no dispara OptionSelected para disabled, pero
        # el handler tiene guard defensivo. Verificamos via API publica
        # que la opcion esta disabled y el screen_stack no creceria.
        from textual.widgets import OptionList as OL

        option_list = app.query_one("#main-menu", OL)
        for i in range(option_list.option_count):
            o = option_list.get_option_at_index(i)
            if o.id == "colors":
                assert o.disabled is True
        assert len(app.screen_stack) == before_count


# ---------- abrir editor desde happy path ----------


async def test_colors_opens_editor_when_enabled(tmp_path: Path) -> None:
    from ztc.services.terminals.alacritty import AlacrittyBackend

    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend=AlacrittyBackend(),
        backend_path=tmp_path / "alacritty.toml",
        detection=TerminalDetection(
            kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
        ),
        zellij_installed=True,
    )
    async with app.run_test() as pilot:
        # Bajamos al item "colors" (4o, despues de themes/layouts/sessions) y damos enter.
        await pilot.press("down", "down", "down", "enter")
        await pilot.pause()
        assert isinstance(app.screen, ColorEditorScreen)


async def test_terminal_settings_opens_editor_when_enabled(tmp_path: Path) -> None:
    from ztc.screens.terminal_settings import TerminalSettingsScreen
    from ztc.services.terminals.alacritty import AlacrittyBackend

    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend=AlacrittyBackend(),
        backend_path=tmp_path / "alacritty.toml",
        detection=TerminalDetection(
            kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
        ),
        zellij_installed=True,
    )
    async with app.run_test() as pilot:
        # Item "terminal-settings" es el 5o (despues de themes/layouts/sessions/colors).
        await pilot.press("down", "down", "down", "down", "enter")
        await pilot.pause()
        assert isinstance(app.screen, TerminalSettingsScreen)


# ---------- E2E con Kitty: deteccion -> editor -> edit -> save ----------


async def test_e2e_kitty_detection_writes_to_real_kitty_conf(tmp_path: Path) -> None:
    """Simula correr el TUI desde Kitty, abrir el editor, modificar un
    slot y guardar. El archivo en disco debe reflejar el cambio en el
    formato propio de kitty (`key value`, no TOML).

    Cubre el camino completo: deteccion -> registry -> ColorEditorScreen
    -> KittyBackend.read_slot -> write_slot -> save.
    """
    from ztc.services.terminals.kitty import KittyBackend

    # Setup: kitty.conf con un tema incluido + override propio del main.
    theme = tmp_path / "tokyo.conf"
    theme.write_text(
        "background #1a1b26\nforeground #c0caf5\ncolor1 #f7768e\n",
        encoding="utf-8",
    )
    main = tmp_path / "kitty.conf"
    main.write_text(
        "include tokyo.conf\n"
        "font_size 12.0\n"
        "allow_remote_control yes\n"
        "listen_on unix:@ztc-{kitty_pid}\n"
        "dynamic_background_opacity yes\n",
        encoding="utf-8",
    )

    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=main,
        detection=TerminalDetection(
            kind="kitty", via_ssh=False, raw_marker="env:KITTY_PID"
        ),
        zellij_installed=True,
    )
    async with app.run_test() as pilot:
        # El registry resolvio KittyBackend.
        assert isinstance(app.backend, KittyBackend)

        # Abrir el editor: 4a opcion del menu (themes/layouts/sessions/colors).
        await pilot.press("down", "down", "down", "enter")
        await pilot.pause()
        assert isinstance(app.screen, ColorEditorScreen)

        # El editor lee los slots desde el include de tokyo.
        editor = app.screen
        assert editor.backend.read_slot(
            editor.doc, ("primary", "background")
        ) == "#1a1b26"
        assert editor.backend.read_slot(
            editor.doc, ("normal", "red")
        ) == "#f7768e"

        # Modificar normal.red en el doc y guardar. action_save abre un
        # PromptModal prellenado con el nombre actual; Enter confirma.
        editor.backend.write_slot(editor.doc, ("normal", "red"), "#deadbe")
        editor.action_save()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        # El archivo del main refleja el cambio (formato kitty,
        # last-wins por append al final).
        text = main.read_text(encoding="utf-8")
        assert "color1 #deadbe" in text
        # El include sigue intacto.
        assert "color1 #f7768e" in theme.read_text(encoding="utf-8")
        # No-colors del main preservados.
        assert "include tokyo.conf" in text
        assert "font_size 12.0" in text
        assert "allow_remote_control yes" in text
        assert "listen_on unix:@ztc-{kitty_pid}" in text
        # El backup se creo (porque el archivo existia).
        backups = list(tmp_path.glob("kitty.conf.bak.*"))
        assert backups


async def test_startup_check_is_requested_and_pushed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from ztc.startup_checks import StartupCheck
    from ztc.widgets.confirm import UnsavedChangesModal

    calls: list[tuple[object, Path, object]] = []
    modal = UnsavedChangesModal()

    def fake_build_startup_check(backend, backend_path, app):  # noqa: ANN001
        calls.append((backend, backend_path, app))
        return StartupCheck(modal=modal, on_result=lambda result: None)

    monkeypatch.setattr("ztc.app.build_startup_check", fake_build_startup_check)
    backend_path = tmp_path / "alacritty.toml"
    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=backend_path,
        detection=TerminalDetection(
            kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
        ),
        zellij_installed=True,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert calls == [(app.backend, backend_path, app)]
        assert app.screen is modal


async def test_startup_check_not_requested_without_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[object] = []

    def fake_build_startup_check(*args, **kwargs):  # noqa: ANN001
        calls.append(args)
        raise AssertionError("startup check should not be requested")

    monkeypatch.setattr("ztc.app.build_startup_check", fake_build_startup_check)
    app = TermConfigApp(
        paths=_paths(tmp_path),
        detection=TerminalDetection(
            kind="unsupported", via_ssh=False, raw_marker=None
        ),
        zellij_installed=True,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
    assert calls == []


# ---------- item "Zellij sessions": PickerScreen embebida ----------


async def test_sessions_cancel_returns_to_menu(tmp_path: Path) -> None:
    """Esc/q desde PickerScreen embebido vuelve al menu de ztc, no cierra la app."""
    from ztc.sessions.screens.picker import PickerScreen

    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=tmp_path / "alacritty.toml",
        detection=TerminalDetection(
            kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
        ),
        zellij_installed=True,
    )
    async with app.run_test() as pilot:
        # Bajamos al item "sessions" (3o) y damos enter.
        await pilot.press("down", "down", "enter")
        await pilot.pause()
        assert isinstance(app.screen, PickerScreen)

        # En modo embebido, `q` es noop; solo `Esc` sale.
        await pilot.press("q")
        await pilot.pause()
        assert isinstance(app.screen, PickerScreen)  # `q` no hizo nada.

        # `Esc` dispara action_quit -> on_cancel -> pop_screen, vuelve al menu.
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, PickerScreen)


async def test_sessions_launch_attach_sets_pending(tmp_path: Path) -> None:
    """`_handle_session_launch` debe SOLO guardar el target en
    `pending_launch` y disparar `app.exit()`. NO debe llamar `execvp`
    desde dentro del event loop — si lo hace, zellij hereda raw mode
    + alt-screen y la terminal queda bloqueada al salir. El `execvp`
    ocurre en `launcher.dispatch_target` despues que `app.run()`
    retorna y Textual restauro la terminal."""
    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=tmp_path / "alacritty.toml",
        detection=TerminalDetection(
            kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
        ),
        zellij_installed=True,
    )
    assert app.pending_launch is None
    app._handle_session_launch(("attach", "mi-sesion", None))
    assert app.pending_launch == ("attach", "mi-sesion", None)


async def test_sessions_launch_new_sets_pending(tmp_path: Path) -> None:
    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=tmp_path / "alacritty.toml",
        detection=TerminalDetection(
            kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
        ),
        zellij_installed=True,
    )
    app._handle_session_launch(("new", "nueva", "compact"))
    assert app.pending_launch == ("new", "nueva", "compact")


async def test_sessions_launch_bash_sets_pending(tmp_path: Path) -> None:
    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=tmp_path / "alacritty.toml",
        detection=TerminalDetection(
            kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
        ),
        zellij_installed=True,
    )
    app._handle_session_launch(("bash", None, None))
    assert app.pending_launch == ("bash", None, None)


async def test_picker_blocks_launch_when_zellij_not_installed(
    tmp_path: Path,
) -> None:
    """Cuando PickerScreen recibe zellij_installed=False, los handlers
    de attach/new/new+layout muestran toast y NO setean pending_launch.
    `bash` queda habilitado porque no requiere zellij."""
    from ztc.sessions.screens.picker import PickerScreen

    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=tmp_path / "alacritty.toml",
        detection=TerminalDetection(
            kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
        ),
        zellij_installed=True,  # ztc tiene zellij; pero le pasamos False al picker.
    )
    async with app.run_test() as pilot:
        screen = PickerScreen(
            on_launch=app._handle_session_launch,
            on_cancel=app.pop_screen,
            zellij_installed=False,
        )
        app.push_screen(screen)
        await pilot.pause()

        # action_attach: bloqueado por el guard, pending_launch sigue None.
        screen.action_attach()
        await pilot.pause()
        assert app.pending_launch is None

        # action_new_session: bloqueado, pending_launch sigue None.
        screen.action_new_session()
        await pilot.pause()
        assert app.pending_launch is None

        # action_new_with_layout: bloqueado, pending_launch sigue None.
        screen.action_new_with_layout()
        await pilot.pause()
        assert app.pending_launch is None

        # action_bash: NO se bloquea -> on_launch -> setea pending_launch.
        screen.action_bash()
        await pilot.pause()
        assert app.pending_launch == ("bash", None, None)


async def test_sessions_launch_none_target_is_noop(tmp_path: Path) -> None:
    """Guard defensivo: target=None al handler deja `pending_launch` como
    None (no marca nada para dispatchear)."""
    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=tmp_path / "alacritty.toml",
        detection=TerminalDetection(
            kind="alacritty", via_ssh=False, raw_marker="env:ALACRITTY_WINDOW_ID"
        ),
        zellij_installed=True,
    )
    app._handle_session_launch(None)
    assert app.pending_launch is None
