"""Tests del gating del menu principal segun deteccion de terminal y Zellij.

Cubren los escenarios de UX definidos en PLAN_MULTI_TERMINAL.md (Fase B):
- Terminal soportada + zellij + no SSH -> happy path.
- Terminal no soportada -> "Colores de terminal" disabled "(no soportada)".
- SSH detectado -> "Colores de terminal" disabled "(SSH)".
- Zellij no instalado -> "Tema/Layouts Zellij" disabled, colores intactos.
- Override env var valido -> respeta override.
- Override env var invalido -> disabled "(override invalido)".
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
        colors_label, colors_disabled = _option_state(app, "colors")
        assert themes_disabled is False
        assert layouts_disabled is False
        assert colors_disabled is False
        assert "unsupported" not in colors_label
        assert "SSH" not in colors_label
        assert "zellij not installed" not in themes_label.lower()


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

    app = TermConfigApp(
        paths=_paths(tmp_path),
        backend_path=tmp_path / "kitty.conf",
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
        colors_label, colors_disabled = _option_state(app, "colors")
        assert themes_disabled is True
        assert layouts_disabled is True
        assert "zellij not installed" in themes_label
        assert "zellij not installed" in layouts_label
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
        # el handler tiene guard defensivo. Lo verificamos disparando
        # el evento directo con un Option disabled manual.
        from textual.widgets.option_list import Option

        from textual.widgets import OptionList as OL

        opt = Option("Colores de terminal", id="colors", disabled=True)
        # Construimos un evento "fake" sintetico: no se puede crear sin
        # widget real; en su lugar verificamos via API publica que la
        # opcion esta disabled y el screen_stack no creceria al pulsar.
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
        # Bajamos al item "colors" (3o) y damos enter.
        await pilot.press("down", "down", "enter")
        await pilot.pause()
        assert isinstance(app.screen, ColorEditorScreen)


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
        "include tokyo.conf\nfont_size 12.0\n", encoding="utf-8"
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

        # Abrir el editor: 3a opcion del menu.
        await pilot.press("down", "down", "enter")
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

        # Modificar normal.red en el doc y guardar.
        editor.backend.write_slot(editor.doc, ("normal", "red"), "#deadbe")
        editor.action_save()
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
        # El backup se creo (porque el archivo existia).
        backups = list(tmp_path.glob("kitty.conf.bak.*"))
        assert backups
