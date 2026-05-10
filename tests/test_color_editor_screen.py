"""Tests del ColorEditorScreen.

Inicialmente vacio. Stage A de v1.2.0 (Kitty import parity) agrega los
primeros tests para el flujo de import: confirma que removido el guard
`isinstance(AlacrittyBackend)`, el callback de import funciona para
ambos backends."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult

from ztc.screens.color_editor import ColorEditorScreen
from ztc.services.save_helper import SaveResult
from ztc.services.terminals.kitty import KittyBackend


class _Harness(App[None]):
    """App minima que monta el screen para testing aislado."""

    def __init__(self, screen: ColorEditorScreen) -> None:
        super().__init__()
        self._screen = screen

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        self.push_screen(self._screen)


def _kitty_doc(tmp_path: Path, content: str = "") -> Path:
    p = tmp_path / "kitty.conf"
    p.write_text(content, encoding="utf-8")
    return p


# ---------- Stage A: import flow para Kitty ----------


async def test_action_import_works_with_kitty_backend(tmp_path: Path) -> None:
    """Antes: `action_import` salia early con toast "not supported" para
    Kitty. Stage A removio el guard — Kitty ahora tiene `import_theme_file`
    en la Protocol.

    Verificamos que el callback que `action_import` pasa a `push_screen`,
    al ser invocado con un path source valido, copia color slots al doc."""
    backend = KittyBackend()

    # Source `.conf` con colores distintos al destino.
    source = tmp_path / "source.conf"
    source.write_text(
        "background #112233\n"
        "foreground #aabbcc\n"
        "color1 #ff0000\n",
        encoding="utf-8",
    )

    # Doc destino con valores diferentes.
    dst = _kitty_doc(
        tmp_path,
        "background #1e1e2e\nforeground #cdd6f4\ncolor1 #f38ba8\n",
    )
    zellij_cfg = tmp_path / "config.kdl"
    zellij_cfg.write_text("// empty\n", encoding="utf-8")

    screen = ColorEditorScreen(
        backend=backend, backend_path=dst, zellij_config_path=zellij_cfg
    )
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

        # Color slots importados quedaron en el doc + screen marcado dirty.
        assert backend.read_slot(screen.doc, ("primary", "background")) == "#112233"
        assert backend.read_slot(screen.doc, ("primary", "foreground")) == "#aabbcc"
        assert backend.read_slot(screen.doc, ("normal", "red")) == "#ff0000"
        assert screen.dirty is True


async def test_action_save_uses_save_helper(tmp_path: Path, monkeypatch) -> None:
    backend = KittyBackend()
    dst = _kitty_doc(tmp_path, "background #1e1e2e\n")
    zellij_cfg = tmp_path / "config.kdl"
    zellij_cfg.write_text("// empty\n", encoding="utf-8")
    screen = ColorEditorScreen(
        backend=backend, backend_path=dst, zellij_config_path=zellij_cfg
    )
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
        return "composed toast"

    monkeypatch.setattr(
        "ztc.screens.color_editor.save_with_reload",
        fake_save_with_reload,
    )
    monkeypatch.setattr(
        "ztc.screens.color_editor.compose_save_toast",
        fake_compose_save_toast,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        app.notify = lambda message, **kwargs: notifications.append(message)  # type: ignore[method-assign]
        screen.dirty = True
        screen.action_save()
        await pilot.pause()

    assert calls == [(backend, screen.doc, dst)]
    assert screen.dirty is False
    assert notifications == ["composed toast"]
