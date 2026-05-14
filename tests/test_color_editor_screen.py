"""Tests del flow Load/Save de ColorEditorScreen (Fase F+G).

Cubre:
- action_save con nombre actual (Enter directo) → save in-place + disk write.
- action_save validacion: extension equivocada rechazada.
- action_load happy path: switch + state update.
- action_load con dirty=True dispara UnsavedChangesModal.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult

from ztc.screens.color_editor import ColorEditorScreen
from ztc.services.terminals.alacritty import AlacrittyBackend


class _Harness(App[None]):
    """App minima que monta el screen y expone backend_manifest_path
    para que las acciones (que consultan `self.app.backend_manifest_path`)
    no exploten."""

    def __init__(
        self,
        screen: ColorEditorScreen,
        *,
        manifest_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._screen = screen
        # En tests sin manifest separado, manifest_path apunta al mismo
        # archivo que el perfil activo (caso config standalone).
        self.backend_manifest_path: Path | None = (
            manifest_path or screen.backend_path
        )
        self.notifications: list[tuple[str, str]] = []
        # Proxy: set_active_profile no es metodo de App por default; el
        # screen lo llama via self.app.set_active_profile.
        self.set_active_profile_calls: list[Path] = []

    def set_active_profile(self, new_profile_path: Path) -> None:
        self.set_active_profile_calls.append(new_profile_path)

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        self.push_screen(self._screen)

    def notify(self, message: str, **kwargs: object) -> None:  # type: ignore[override]
        self.notifications.append(
            (str(message), str(kwargs.get("severity", "information")))
        )


def _setup_screen(
    tmp_path: Path, content: str = '[colors.primary]\nbackground = "#000000"\n'
) -> tuple[ColorEditorScreen, Path, Path]:
    backend = AlacrittyBackend()
    path = tmp_path / "alacritty.toml"
    path.write_text(content, encoding="utf-8")
    zcfg = tmp_path / "config.kdl"
    zcfg.write_text("// empty\n", encoding="utf-8")
    screen = ColorEditorScreen(
        backend=backend, backend_path=path, zellij_config_path=zcfg
    )
    return screen, path, zcfg


# ---------- action_save: modal + save in-place ----------


async def test_action_save_same_name_saves_in_place(tmp_path: Path) -> None:
    """Enter directo en el PromptModal (nombre actual prellenado) saves
    in-place: el archivo en disco refleja el cambio y dirty queda False."""
    screen, path, _ = _setup_screen(tmp_path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Modificar in-memory y marcar dirty.
        screen.backend.write_slot(
            screen.doc, ("primary", "background"), "#abcdef"
        )
        screen.dirty = True
        screen.action_save()
        await pilot.pause()
        # PromptModal activo con "alacritty.toml" prellenado. Enter confirma.
        await pilot.press("enter")
        await pilot.pause()
        # Archivo en disco tiene el nuevo color.
        loaded = screen.backend.load(path)
        assert (
            screen.backend.read_slot(loaded, ("primary", "background"))
            == "#abcdef"
        )
        assert screen.dirty is False


async def test_action_save_rejects_wrong_extension(tmp_path: Path) -> None:
    """Nombre con extension distinta a .toml rechazado con error toast.
    El archivo no se escribe."""
    screen, path, _ = _setup_screen(tmp_path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.dirty = True
        screen.action_save()
        await pilot.pause()
        # En el modal, escribir un nombre con extension equivocada.
        from textual.widgets import Input

        inp = app.screen.query_one("#prompt-input", Input)
        inp.value = "wrong.conf"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # Error notify con mensaje de extension.
        errors = [n for n in app.notifications if n[1] == "error"]
        assert any(".toml" in msg for msg, _ in errors)
        # No se creo el archivo wrong.conf.
        assert not (tmp_path / "wrong.conf").exists()


# ---------- action_load: switch profile ----------


async def test_action_load_switches_active_profile(tmp_path: Path) -> None:
    """Load valido en un manifest gestionado: doc actualizado, backend_path
    asignado al nuevo perfil, set_active_profile invocado en el app."""
    backend = AlacrittyBackend()
    manifest = tmp_path / "alacritty.toml"
    manifest.write_text(
        "[ztc]\nmanaged_manifest = true\n\n"
        '[general]\nimport = ["c64.toml"]\n',
        encoding="utf-8",
    )
    c64 = tmp_path / "c64.toml"
    c64.write_text(
        '[colors.primary]\nbackground = "#9190ef"\n', encoding="utf-8"
    )
    vga = tmp_path / "vga.toml"
    vga.write_text(
        '[colors.primary]\nbackground = "#0000aa"\n', encoding="utf-8"
    )
    zcfg = tmp_path / "config.kdl"
    zcfg.write_text("// empty\n", encoding="utf-8")
    screen = ColorEditorScreen(
        backend=backend, backend_path=c64, zellij_config_path=zcfg
    )
    app = _Harness(screen, manifest_path=manifest)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.action_load()
        await pilot.pause()
        # PromptModal pidiendo path. Escribir "vga.toml" y confirmar.
        from textual.widgets import Input

        inp = app.screen.query_one("#prompt-input", Input)
        inp.value = "vga.toml"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # set_active_profile invocado con el nuevo path.
        assert app.set_active_profile_calls == [vga]
        # Screen state actualizado.
        assert screen.backend_path == vga
        assert screen.dirty is False
        # El doc tiene los slots del nuevo perfil.
        assert (
            backend.read_slot(screen.doc, ("primary", "background"))
            == "#0000aa"
        )


async def test_action_load_dirty_opens_unsaved_changes_modal(tmp_path: Path) -> None:
    """Con cambios sin guardar, action_load NO abre el PromptModal de path
    sino el UnsavedChangesModal primero."""
    from ztc.widgets.confirm import UnsavedChangesModal

    screen, _, _ = _setup_screen(tmp_path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.dirty = True
        screen.action_load()
        await pilot.pause()
        assert isinstance(app.screen, UnsavedChangesModal)


async def test_action_load_nonexistent_file_shows_error(tmp_path: Path) -> None:
    """Path que no existe → error toast, sin tocar state."""
    screen, _, _ = _setup_screen(tmp_path)
    app = _Harness(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen.action_load()
        await pilot.pause()
        from textual.widgets import Input

        inp = app.screen.query_one("#prompt-input", Input)
        inp.value = "missing.toml"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        errors = [n for n in app.notifications if n[1] == "error"]
        assert any("Does not exist" in msg for msg, _ in errors)
        # set_active_profile NO se llamo.
        assert app.set_active_profile_calls == []
