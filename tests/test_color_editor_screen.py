"""Tests del ColorEditorScreen."""

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
