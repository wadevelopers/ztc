from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static


class ConfirmActionModal(ModalScreen[bool]):
    """Confirma una accion destructiva con botones No/Yes.

    El foco inicial queda en No para que Enter no confirme por accidente.
    """

    BINDINGS = [Binding("escape", "dismiss_false", "Cancel")]

    DEFAULT_CSS = """
    ConfirmActionModal {
        align: center middle;
    }
    #dialog {
        width: 70;
        height: auto;
        border: round $error;
        padding: 1 2;
        background: $surface;
    }
    #title {
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }
    #message {
        margin-bottom: 1;
    }
    #buttons {
        align-horizontal: right;
        height: 3;
    }
    """

    def __init__(
        self,
        *,
        title: str,
        message: str,
        confirm_label: str = "Confirm",
    ) -> None:
        super().__init__()
        self._title = title
        self._message = message
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._title, id="title")
            yield Static(self._message, id="message")
            with Horizontal(id="buttons"):
                yield Button("No", id="cancel")
                yield Button(self._confirm_label, id="confirm", variant="error")

    def on_mount(self) -> None:
        self.query_one("#cancel", Button).focus()

    @on(Button.Pressed, "#confirm")
    def _on_confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def _on_cancel(self) -> None:
        self.dismiss(False)

    def action_dismiss_false(self) -> None:
        self.dismiss(False)


class ConfirmByNameModal(ModalScreen[bool]):
    """Confirma una acción destructiva pidiendo escribir el nombre objetivo."""

    BINDINGS = [Binding("escape", "dismiss_false", "Cancel")]

    DEFAULT_CSS = """
    ConfirmByNameModal {
        align: center middle;
    }
    #dialog {
        width: 70;
        height: auto;
        border: round $error;
        padding: 1 2;
        background: $surface;
    }
    #title {
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }
    Input {
        margin: 1 0;
    }
    #buttons {
        align-horizontal: right;
        height: 3;
    }
    """

    def __init__(
        self,
        *,
        title: str,
        message: str,
        expected: str,
        confirm_label: str = "Confirm",
    ) -> None:
        super().__init__()
        self._title = title
        self._message = message
        self._expected = expected
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._title, id="title")
            yield Static(self._message)
            yield Static(f"Type '[b]{self._expected}[/b]' to confirm:")
            yield Input(placeholder=self._expected, id="confirm-input")
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button(
                    self._confirm_label,
                    id="confirm",
                    variant="error",
                    disabled=True,
                )

    def on_mount(self) -> None:
        self.query_one("#confirm-input", Input).focus()

    @on(Input.Changed, "#confirm-input")
    def _on_change(self, event: Input.Changed) -> None:
        self.query_one("#confirm", Button).disabled = event.value != self._expected

    @on(Input.Submitted, "#confirm-input")
    def _on_submit(self, event: Input.Submitted) -> None:
        if event.value == self._expected:
            self.dismiss(True)

    @on(Button.Pressed, "#confirm")
    def _on_confirm_by_name(self) -> None:
        if self.query_one("#confirm-input", Input).value == self._expected:
            self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def _on_cancel_by_name(self) -> None:
        self.dismiss(False)

    def action_dismiss_false(self) -> None:
        self.dismiss(False)


@dataclass
class NewSessionResult:
    name: str
    layout: str | None


class NewSessionModal(ModalScreen[NewSessionResult | None]):
    """Pide nombre de sesión y, si `layouts` no está vacío, también layout."""

    BINDINGS = [Binding("escape", "dismiss_none", "Cancel")]

    DEFAULT_CSS = """
    NewSessionModal {
        align: center middle;
    }
    #dialog {
        width: 70;
        height: auto;
        border: round $accent;
        padding: 1 2;
        background: $surface;
    }
    #title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    .label {
        color: $text-muted;
    }
    Input, Select {
        margin: 0 0 1 0;
    }
    #buttons {
        align-horizontal: right;
        height: 3;
    }
    """

    def __init__(
        self,
        *,
        title: str = "New session",
        default_name: str = "main",
        layouts: list[str] | None = None,
        default_layout: str | None = None,
        confirm_label: str = "Create",
    ) -> None:
        super().__init__()
        self._title = title
        self._default_name = default_name
        self._layouts = layouts or []
        self._default_layout = default_layout
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._title, id="title")
            yield Static("Name:", classes="label")
            yield Input(value=self._default_name, id="name-input")
            if self._layouts:
                yield Static("Layout:", classes="label")
                initial = self._default_layout if self._default_layout in self._layouts else None
                yield Select(
                    [(layout, layout) for layout in self._layouts],
                    value=initial or Select.BLANK,
                    id="layout-select",
                    allow_blank=False,
                )
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button(self._confirm_label, id="create", variant="primary")

    def on_mount(self) -> None:
        inp = self.query_one("#name-input", Input)
        inp.focus()
        inp.cursor_position = len(inp.value)

    @on(Input.Changed, "#name-input")
    def _on_name_change(self, event: Input.Changed) -> None:
        self.query_one("#create", Button).disabled = not event.value.strip()

    @on(Input.Submitted, "#name-input")
    def _on_name_submit(self) -> None:
        self._submit()

    @on(Button.Pressed, "#create")
    def _on_create(self) -> None:
        self._submit()

    @on(Button.Pressed, "#cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        name = self.query_one("#name-input", Input).value.strip()
        if not name:
            return
        layout: str | None = None
        if self._layouts:
            value = self.query_one("#layout-select", Select).value
            if isinstance(value, str):
                layout = value
        self.dismiss(NewSessionResult(name=name, layout=layout))
