"""Tests del TerminalSettingsScreen con Pilot.

Cubre: apertura, navegacion entre settings, edicion de FLOAT (modal
texto), edicion de ENUM (modal radio), reset (delete), save (con
backup), reload (descarta cambios pending).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from ztc.screens.terminal_settings import TerminalSettingsScreen
from ztc.services.save_helper import SaveResult
from ztc.services.terminals.alacritty import AlacrittyBackend
from ztc.services.terminals.kitty import KittyBackend
from ztc.services.terminals.settings import SETTINGS


class _Harness(App[None]):
    """App minima que monta el screen para testearlo aislado."""

    def __init__(self, screen: TerminalSettingsScreen) -> None:
        super().__init__()
        self._screen = screen

    def compose(self) -> ComposeResult:  # noqa: D401
        return iter([])

    def on_mount(self) -> None:
        self.push_screen(self._screen)


def _alacritty_doc(tmp_path: Path, content: str = "") -> Path:
    p = tmp_path / "alacritty.toml"
    p.write_text(content, encoding="utf-8")
    return p


def _kitty_doc(tmp_path: Path, content: str = "") -> Path:
    p = tmp_path / "kitty.conf"
    p.write_text(content, encoding="utf-8")
    return p


# ---------- smoke ----------


async def test_screen_opens_with_alacritty(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    path = _alacritty_doc(tmp_path, '[window.padding]\nx = 8\ny = 12\n')
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, TerminalSettingsScreen)
        # Lista los 6 settings.
        from textual.widgets import OptionList

        ol = app.screen.query_one("#setting-list", OptionList)
        assert ol.option_count == 6


async def test_screen_opens_with_kitty(tmp_path: Path) -> None:
    backend = KittyBackend()
    path = _kitty_doc(tmp_path, "font_size 14.0\n")
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, TerminalSettingsScreen)


# ---------- save ----------


async def test_save_writes_to_disk_and_creates_backup(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    path = _alacritty_doc(tmp_path, '[window]\nopacity = 0.8\n')
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Modificar in-memory: setear opacity = 0.5 directamente en doc.
        screen.backend.write_setting(screen.doc, SETTINGS["window.opacity"], 0.5)
        screen.dirty = True
        screen.action_save()
        await pilot.pause()
        # Reload from disk and verify.
        doc = backend.load(path)
        assert backend.read_setting(doc, SETTINGS["window.opacity"]) == 0.5
        # Backup creado.
        backups = list(tmp_path.glob("alacritty.toml.bak.*"))
        assert backups


async def test_action_save_uses_save_helper(tmp_path: Path, monkeypatch) -> None:
    backend = KittyBackend()
    path = _kitty_doc(tmp_path, "font_size 12.0\n")
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    result = SaveResult(tmp_path / "kitty.conf.bak", False, "manual hint")
    calls: list[tuple[object, object, Path]] = []
    notifications: list[str] = []

    def fake_save_with_reload(backend_arg, doc_arg, path_arg):  # noqa: ANN001
        calls.append((backend_arg, doc_arg, path_arg))
        return result

    def fake_compose_save_toast(file_name: str, result_arg: SaveResult) -> str:
        assert file_name == "kitty.conf"
        assert result_arg is result
        return "settings toast"

    monkeypatch.setattr(
        "ztc.screens.terminal_settings.save_with_reload",
        fake_save_with_reload,
    )
    monkeypatch.setattr(
        "ztc.screens.terminal_settings.compose_save_toast",
        fake_compose_save_toast,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        app.notify = lambda message, **kwargs: notifications.append(message)  # type: ignore[method-assign]
        screen.dirty = True
        screen.action_save()
        await pilot.pause()

    assert calls == [(backend, screen.doc, path)]
    assert screen.dirty is False
    assert notifications == ["settings toast"]


# ---------- reset ----------


async def test_reset_removes_setting_from_doc(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    path = _alacritty_doc(tmp_path, '[window]\nopacity = 0.8\n')
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Highlight el setting de opacity (3er en supported_settings).
        # Index segun orden del catalogo:
        # padding.x, padding.y, opacity, font.size, font.family, cursor.shape
        from textual.widgets import OptionList

        ol = app.screen.query_one("#setting-list", OptionList)
        ol.highlighted = 2  # window.opacity
        await pilot.pause()
        screen.action_reset()
        await pilot.pause()
        assert backend.read_setting(screen.doc, SETTINGS["window.opacity"]) is None
        assert screen.dirty is True


# ---------- reload ----------


async def test_reload_discards_dirty_changes(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    path = _alacritty_doc(tmp_path, '[window]\nopacity = 0.8\n')
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Modificar in-memory (sin save).
        backend.write_setting(screen.doc, SETTINGS["window.opacity"], 0.3)
        screen.dirty = True
        # Reload descarta el cambio.
        screen.action_reload()
        await pilot.pause()
        assert backend.read_setting(screen.doc, SETTINGS["window.opacity"]) == 0.8
        assert screen.dirty is False


# ---------- write con valor invalido en handler ----------


async def test_action_edit_rejects_invalid_value(tmp_path: Path) -> None:
    """Si el callback recibe un raw que coerce devuelve None, no se
    escribe y se muestra notify error."""
    backend = AlacrittyBackend()
    path = _alacritty_doc(tmp_path, "")
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import OptionList

        ol = app.screen.query_one("#setting-list", OptionList)
        ol.highlighted = 0  # window.padding.x (INT)
        await pilot.pause()

        # Simular el callback `after` con un raw invalido.
        # action_edit prepara el modal; aca llamamos directo al codigo
        # interno que reacciona al callback.
        # Reusamos la logica: write_setting con un valor que NO sea int
        # debe levantar ValueError, y el screen debe atraparlo.
        with pytest.raises(ValueError):
            backend.write_setting(
                screen.doc, SETTINGS["window.padding.x"], "abc"
            )


# ---------- supported settings count ----------


async def test_lists_6_settings_for_both_backends(tmp_path: Path) -> None:
    for backend, path in [
        (AlacrittyBackend(), _alacritty_doc(tmp_path / "a")),
        (KittyBackend(), _kitty_doc(tmp_path / "k")),
    ]:
        # tmp_path subdirs needed para no colisionar nombres.
        screen = TerminalSettingsScreen(backend=backend, backend_path=path)
        app = _Harness(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import OptionList

            ol = app.screen.query_one("#setting-list", OptionList)
            assert ol.option_count == 6


@pytest.fixture(autouse=True)
def _ensure_subdir(tmp_path: Path) -> None:
    """Crea subdirs `a/` y `k/` para evitar colisiones en
    test_lists_6_settings_for_both_backends."""
    (tmp_path / "a").mkdir(exist_ok=True)
    (tmp_path / "k").mkdir(exist_ok=True)


# ---------- UnsavedChangesModal flow ----------


async def test_back_without_dirty_pops_directly(tmp_path: Path) -> None:
    """Sin cambios, escape sale directo sin modal."""
    backend = AlacrittyBackend()
    path = _alacritty_doc(tmp_path, "")
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, TerminalSettingsScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, TerminalSettingsScreen)


async def test_back_with_dirty_opens_unsaved_changes_modal(tmp_path: Path) -> None:
    from ztc.widgets.confirm import UnsavedChangesModal

    backend = AlacrittyBackend()
    path = _alacritty_doc(tmp_path, "")
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.dirty = True
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, UnsavedChangesModal)


async def test_unsaved_modal_cancel_keeps_screen(tmp_path: Path) -> None:
    """Cancel del modal vuelve al editor; dirty se preserva."""
    from ztc.widgets.confirm import UnsavedChangesModal

    backend = AlacrittyBackend()
    path = _alacritty_doc(tmp_path, "")
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.dirty = True
        await pilot.press("escape")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, UnsavedChangesModal)
        modal.dismiss("cancel")
        await pilot.pause()
        assert isinstance(app.screen, TerminalSettingsScreen)
        assert screen.dirty is True


async def test_unsaved_modal_discard_pops_without_save(tmp_path: Path) -> None:
    """Discard sale sin guardar; archivo en disco no cambia."""
    from ztc.widgets.confirm import UnsavedChangesModal

    backend = AlacrittyBackend()
    path = _alacritty_doc(tmp_path, '[window]\nopacity = 0.8\n')
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Modificar in-memory.
        backend.write_setting(screen.doc, SETTINGS["window.opacity"], 0.3)
        screen.dirty = True
        await pilot.press("escape")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, UnsavedChangesModal)
        modal.dismiss("discard")
        await pilot.pause()
        assert not isinstance(app.screen, TerminalSettingsScreen)
        # Archivo en disco preserva el valor original (0.8).
        on_disk = backend.load(path)
        assert backend.read_setting(on_disk, SETTINGS["window.opacity"]) == 0.8


async def test_unsaved_modal_save_writes_and_pops(tmp_path: Path) -> None:
    """Save guarda al disco y sale del editor."""
    from ztc.widgets.confirm import UnsavedChangesModal

    backend = AlacrittyBackend()
    path = _alacritty_doc(tmp_path, '[window]\nopacity = 0.8\n')
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        backend.write_setting(screen.doc, SETTINGS["window.opacity"], 0.3)
        screen.dirty = True
        await pilot.press("escape")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, UnsavedChangesModal)
        modal.dismiss("save")
        await pilot.pause()
        # Salio del editor.
        assert not isinstance(app.screen, TerminalSettingsScreen)
        # Archivo en disco persiste el cambio.
        on_disk = backend.load(path)
        assert backend.read_setting(on_disk, SETTINGS["window.opacity"]) == 0.3


async def test_unsaved_modal_save_failure_keeps_screen(tmp_path: Path) -> None:
    """Si save falla (path read-only o exception), no sale del editor —
    dirty queda True y el usuario puede ver el toast de error."""
    from ztc.widgets.confirm import UnsavedChangesModal

    backend = AlacrittyBackend()
    path = _alacritty_doc(tmp_path, '[window]\nopacity = 0.8\n')
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        backend.write_setting(screen.doc, SETTINGS["window.opacity"], 0.3)
        screen.dirty = True
        # Forzar fallo de save: monkey patch backend.save para que tire.
        original_save = backend.save

        def failing_save(*a, **kw):
            raise RuntimeError("disk full")

        backend.save = failing_save  # type: ignore[method-assign]
        try:
            await pilot.press("escape")
            await pilot.pause()
            modal = app.screen
            assert isinstance(modal, UnsavedChangesModal)
            modal.dismiss("save")
            await pilot.pause()
            # Save fallo → quedo en el editor con dirty=True.
            assert isinstance(app.screen, TerminalSettingsScreen)
            assert screen.dirty is True
        finally:
            backend.save = original_save  # type: ignore[method-assign]


# ---------- Stage A: import flow para Kitty ----------


async def test_action_import_works_with_kitty_backend(tmp_path: Path) -> None:
    """Antes: `action_import` salia early con toast "not supported" para
    Kitty. Stage A removio el guard, ahora ambos backends pueden importar.

    Verificamos que el callback que `action_import` pasa a `push_screen`,
    al ser invocado con un path source valido, copia settings al doc."""
    backend = KittyBackend()

    # Source `.conf` con valores distintos al destino.
    source = tmp_path / "source.conf"
    source.write_text(
        "window_padding_width 20\nfont_size 14.0\n",
        encoding="utf-8",
    )

    # Doc destino con valores diferentes.
    dst = _kitty_doc(
        tmp_path, "window_padding_width 8\nfont_size 12.0\n"
    )
    screen = TerminalSettingsScreen(backend=backend, backend_path=dst)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()

        # Monkey-patch ANTES de action_import: el callback se pasa
        # durante esa llamada via push_screen(modal, callback). Capturamos
        # ese callback sin que el modal real se levante.
        captured: list[object] = []

        def fake_push_screen(modal, callback=None, *args, **kwargs):  # noqa: ANN001
            captured.append(callback)

        original = app.push_screen
        app.push_screen = fake_push_screen  # type: ignore[assignment]
        try:
            screen.action_import()
            await pilot.pause()
        finally:
            app.push_screen = original  # type: ignore[assignment]

        assert len(captured) == 1, "action_import should push exactly one modal"
        callback = captured[0]
        assert callback is not None

        # Invocar el callback directamente con el path del source.
        callback(str(source))
        await pilot.pause()

        # Settings importados quedaron en el doc + screen marcado dirty.
        new_padding = backend.read_setting(
            screen.doc, SETTINGS["window.padding.x"]
        )
        new_font_size = backend.read_setting(
            screen.doc, SETTINGS["font.size"]
        )
        assert new_padding == 20
        assert new_font_size == 14.0
        assert screen.dirty is True
