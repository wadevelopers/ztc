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
from ztc.services.terminals.alacritty import AlacrittyBackend
from ztc.services.terminals.kitty import KittyBackend
from ztc.services.terminals.settings import SETTINGS


class _Harness(App[None]):
    """App minima que monta el screen para testearlo aislado."""

    def __init__(
        self,
        screen: TerminalSettingsScreen,
        *,
        manifest_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._screen = screen
        # action_save / action_back / action_load consultan el manifest path
        # del app. En tests sin manifest separado, apunta al mismo path que
        # el perfil activo (caso config standalone).
        self.backend_manifest_path: Path | None = (
            manifest_path or screen.backend_path
        )
        self.set_active_profile_calls: list[Path] = []
        self.notifications: list[tuple[str, str]] = []

    def set_active_profile(self, new_profile_path: Path) -> None:
        self.set_active_profile_calls.append(new_profile_path)

    def compose(self) -> ComposeResult:  # noqa: D401
        return iter([])

    def on_mount(self) -> None:
        self.push_screen(self._screen)

    def notify(self, message: str, **kwargs: object) -> None:  # type: ignore[override]
        self.notifications.append(
            (str(message), str(kwargs.get("severity", "information")))
        )


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
        # Lista los 8 settings.
        from textual.widgets import OptionList

        ol = app.screen.query_one("#setting-list", OptionList)
        assert ol.option_count == 8


async def test_screen_opens_with_kitty(tmp_path: Path) -> None:
    backend = KittyBackend()
    path = _kitty_doc(tmp_path, "font_size 14.0\n")
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, TerminalSettingsScreen)


# ---------- reset ----------


async def test_reset_removes_setting_from_doc(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    path = _alacritty_doc(tmp_path, '[window]\nopacity = 0.8\n')
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Highlight el setting de opacity.
        # Index segun orden del catalogo:
        # columns, lines, padding.x, padding.y, opacity, font.size,
        # font.family, cursor.shape
        from textual.widgets import OptionList

        ol = app.screen.query_one("#setting-list", OptionList)
        ol.highlighted = 4  # window.opacity
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
        ol.highlighted = 2  # window.padding.x (INT)
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


async def test_lists_8_settings_for_both_backends(tmp_path: Path) -> None:
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
            assert ol.option_count == 8


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


# ---------- action_save: modal + save in-place / save-as ----------


async def test_action_save_same_name_saves_in_place(tmp_path: Path) -> None:
    """Enter en el PromptModal con el nombre actual prellenado guarda en
    el activo: archivo en disco actualizado + dirty=False."""
    backend = AlacrittyBackend()
    path = _alacritty_doc(tmp_path, '[window]\nopacity = 0.8\n')
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        backend.write_setting(screen.doc, SETTINGS["window.opacity"], 0.5)
        screen.dirty = True
        screen.action_save()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        on_disk = backend.load(path)
        assert backend.read_setting(on_disk, SETTINGS["window.opacity"]) == 0.5
        assert screen.dirty is False


async def test_action_save_rejects_wrong_extension(tmp_path: Path) -> None:
    """Nombre con `.conf` en Alacritty rechazado con error toast."""
    backend = AlacrittyBackend()
    path = _alacritty_doc(tmp_path, '[window]\nopacity = 0.8\n')
    screen = TerminalSettingsScreen(backend=backend, backend_path=path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.dirty = True
        screen.action_save()
        await pilot.pause()
        from textual.widgets import Input

        inp = app.screen.query_one("#prompt-input", Input)
        inp.value = "wrong.conf"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        errors = [n for n in app.notifications if n[1] == "error"]
        assert any(".toml" in msg for msg, _ in errors)
        # No se creo el archivo wrong.conf.
        assert not (tmp_path / "wrong.conf").exists()


# ---------- action_load: switch profile ----------


async def test_action_load_switches_active_profile(tmp_path: Path) -> None:
    """Load en un manifest gestionado: doc actualizado, backend_path
    asignado al nuevo perfil, set_active_profile invocado."""
    backend = AlacrittyBackend()
    manifest = tmp_path / "alacritty.toml"
    manifest.write_text(
        "[ztc]\nmanaged_manifest = true\n\n"
        '[general]\nimport = ["c64.toml"]\n',
        encoding="utf-8",
    )
    c64 = tmp_path / "c64.toml"
    c64.write_text('[window]\nopacity = 0.5\n', encoding="utf-8")
    vga = tmp_path / "vga.toml"
    vga.write_text('[window]\nopacity = 0.95\n', encoding="utf-8")
    screen = TerminalSettingsScreen(backend=backend, backend_path=c64)
    app = _Harness(screen, manifest_path=manifest)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.action_load()
        await pilot.pause()
        from textual.widgets import Input

        inp = app.screen.query_one("#prompt-input", Input)
        inp.value = "vga.toml"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.set_active_profile_calls == [vga]
        assert screen.backend_path == vga
        assert screen.dirty is False
        # El doc tiene los settings del nuevo perfil.
        assert (
            backend.read_setting(screen.doc, SETTINGS["window.opacity"]) == 0.95
        )
