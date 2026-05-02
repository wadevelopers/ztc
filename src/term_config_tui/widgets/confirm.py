from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class ConfirmByNameModal(ModalScreen[bool]):
    """Modal para confirmar acciones destructivas escribiendo el nombre objetivo."""

    BINDINGS = [
        Binding("escape", "dismiss_false", "Cancelar"),
    ]

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
    #message {
        margin-bottom: 1;
    }
    Input {
        margin-bottom: 1;
    }
    #buttons {
        align-horizontal: right;
        height: 3;
    }
    Button {
        margin-left: 1;
    }
    """

    def __init__(
        self,
        *,
        title: str,
        message: str,
        expected: str,
        confirm_label: str = "Confirmar",
    ) -> None:
        super().__init__()
        self._title = title
        self._message = message
        self._expected = expected
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._title, id="title")
            yield Static(self._message, id="message")
            yield Static(
                f"Escribe '[b]{self._expected}[/b]' para confirmar:",
                id="hint",
            )
            yield Input(placeholder=self._expected, id="confirm-input")
            with Horizontal(id="buttons"):
                yield Button("Cancelar", id="cancel", variant="default")
                yield Button(
                    self._confirm_label,
                    id="confirm",
                    variant="error",
                    disabled=True,
                )

    def on_mount(self) -> None:
        self.query_one("#confirm-input", Input).focus()

    @on(Input.Changed, "#confirm-input")
    def _on_input_change(self, event: Input.Changed) -> None:
        button = self.query_one("#confirm", Button)
        button.disabled = event.value != self._expected

    @on(Input.Submitted, "#confirm-input")
    def _on_input_submit(self, event: Input.Submitted) -> None:
        if event.value == self._expected:
            self.dismiss(True)

    @on(Button.Pressed, "#confirm")
    def _on_confirm(self) -> None:
        if self.query_one("#confirm-input", Input).value == self._expected:
            self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def _on_cancel(self) -> None:
        self.dismiss(False)

    def action_dismiss_false(self) -> None:
        self.dismiss(False)


@dataclass
class NewSessionResult:
    name: str
    layout: str | None


class NewSessionModal(ModalScreen[NewSessionResult | None]):
    """Modal con input de nombre y, opcionalmente, selector de layout."""

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancelar"),
    ]

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
    Static.label {
        color: $text-muted;
    }
    Input, Static.label {
        margin-bottom: 1;
    }
    #buttons {
        align-horizontal: right;
        height: 3;
    }
    Button {
        margin-left: 1;
    }
    """

    def __init__(
        self,
        *,
        title: str = "Nueva sesion",
        layouts: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._layouts = layouts or []

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._title, id="title")
            yield Static("Nombre de la sesion:", classes="label")
            yield Input(placeholder="ej. dev", id="name-input")
            if self._layouts:
                yield Static(
                    f"Layout (opcional): {' / '.join(self._layouts)}",
                    classes="label",
                )
                yield Input(placeholder="dejar vacio para layout default", id="layout-input")
            with Horizontal(id="buttons"):
                yield Button("Cancelar", id="cancel")
                yield Button("Crear", id="create", variant="primary", disabled=True)

    def on_mount(self) -> None:
        self.query_one("#name-input", Input).focus()

    @on(Input.Changed, "#name-input")
    def _on_name_change(self, event: Input.Changed) -> None:
        self.query_one("#create", Button).disabled = not event.value.strip()

    @on(Input.Submitted, "#name-input")
    def _on_name_submit(self) -> None:
        self._submit()

    @on(Input.Submitted, "#layout-input")
    def _on_layout_submit(self) -> None:
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
            layout_value = self.query_one("#layout-input", Input).value.strip()
            if layout_value:
                layout = layout_value
        self.dismiss(NewSessionResult(name=name, layout=layout))
