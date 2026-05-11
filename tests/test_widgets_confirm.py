from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Button, Checkbox, Static

from ztc.widgets.confirm import (
    EnumPickerModal,
    FontPickerModal,
    KittyRemoteControlChoice,
    KittyRemoteControlModal,
)


class _Harness(App[None]):
    def __init__(
        self,
        *,
        inside_zellij: bool = False,
        remote_control_missing: bool = True,
        listen_on_missing: bool | None = None,
        dynamic_background_opacity_missing: bool = False,
    ) -> None:
        super().__init__()
        self.modal = KittyRemoteControlModal(
            inside_zellij=inside_zellij,
            remote_control_missing=remote_control_missing,
            listen_on_missing=listen_on_missing,
            dynamic_background_opacity_missing=dynamic_background_opacity_missing,
        )
        self.results: list[KittyRemoteControlChoice | None] = []

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        self.push_screen(self.modal, self.results.append)


class _FontHarness(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.modal = FontPickerModal(
            title="Edit font.family",
            choices=["Fira Code", "JetBrains Mono", "Monaspace Neon"],
            initial="JetBrains Mono",
        )
        self.results: list[str | None] = []

    def compose(self) -> ComposeResult:
        return iter([])

    def on_mount(self) -> None:
        self.push_screen(self.modal, self.results.append)


class _EnumHarness(App[None]):
    def __init__(self, *, initial: str = "Beam") -> None:
        super().__init__()
        self.modal = EnumPickerModal(
            title="Edit cursor.shape",
            choices=("Block", "Beam", "Underline"),
            initial=initial,
        )
        self.results: list[str | None] = []

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


async def test_kitty_remote_control_modal_copy_outside_zellij() -> None:
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        title = app.modal.query_one("#title", Static).content
        message = str(app.modal.query_one("#message", Static).content)
        assert title == "Auto-reload not configured in Kitty"
        assert "automatically refresh your terminal" in message
        assert "listener socket" not in message
        assert "Ctrl + Shift + F5" in message
        assert "allow_remote_control yes" in message
        assert "dynamic_background_opacity yes" not in message
        assert "only the missing setting(s) to kitty.conf" in message
        assert "restart Kitty once" in message
        assert app.modal.query_one("#enable", Button).label.plain == "Yes"
        assert app.modal.query_one("#skip", Button).label.plain == "No"


async def test_kitty_remote_control_modal_copy_inside_zellij() -> None:
    app = _Harness(inside_zellij=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        message = str(app.modal.query_one("#message", Static).content)
        assert "Because ZTC is running inside Zellij" in message
        assert "listener socket" in message
        assert "listen_on unix:@ztc-{kitty_pid}" in message
        assert "only the missing setting(s) to kitty.conf" in message


async def test_kitty_remote_control_modal_copy_for_dynamic_opacity_only() -> None:
    app = _Harness(
        remote_control_missing=False,
        listen_on_missing=False,
        dynamic_background_opacity_missing=True,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        message = str(app.modal.query_one("#message", Static).content)
        assert "allow_remote_control yes" not in message
        assert "listener socket" not in message
        assert "dynamic_background_opacity yes" in message
        assert "Live background opacity changes require" in message


async def test_font_picker_enter_confirms_highlighted_font() -> None:
    app = _FontHarness()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
    assert app.results == ["JetBrains Mono"]


async def test_enum_picker_enter_confirms_selected_value() -> None:
    app = _EnumHarness()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
    assert app.results == ["Beam"]


async def test_enum_picker_enter_confirms_highlighted_value_after_navigation() -> None:
    app = _EnumHarness(initial="Block")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()
    assert app.results == ["Beam"]
