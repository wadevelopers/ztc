from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Checkbox

from ztc.widgets.confirm import KittyRemoteControlChoice, KittyRemoteControlModal


class _Harness(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.modal = KittyRemoteControlModal()
        self.results: list[KittyRemoteControlChoice | None] = []

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        self.push_screen(self.modal, self.results.append)


async def test_kitty_remote_control_modal_enable_ignores_checkbox() -> None:
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.modal.query_one("#remember", Checkbox).value = True
        app.modal._on_enable()
        await pilot.pause()
    assert app.results == [KittyRemoteControlChoice(action="enable")]


async def test_kitty_remote_control_modal_skip_without_checkbox() -> None:
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.modal._on_skip()
        await pilot.pause()
    assert app.results == [
        KittyRemoteControlChoice(action="skip", dont_show_again=False)
    ]


async def test_kitty_remote_control_modal_skip_with_checkbox() -> None:
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.modal.query_one("#remember", Checkbox).value = True
        app.modal._on_skip()
        await pilot.pause()
    assert app.results == [
        KittyRemoteControlChoice(action="skip", dont_show_again=True)
    ]


async def test_kitty_remote_control_modal_escape_returns_none() -> None:
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.modal.action_dismiss_none()
        await pilot.pause()
    assert app.results == [None]


async def test_kitty_remote_control_modal_initial_focus_is_skip() -> None:
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.focused is not None
        assert app.focused.id == "skip"
