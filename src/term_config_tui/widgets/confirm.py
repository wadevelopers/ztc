from __future__ import annotations

import shlex

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, RadioButton, RadioSet, Static, Switch

from term_config_tui.models.layout import Pane, SplitDirection


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


class PromptModal(ModalScreen[str | None]):
    """Modal generico de un solo input: pide texto, devuelve string o None si cancela."""

    BINDINGS = [Binding("escape", "dismiss_none", "Cancelar")]

    DEFAULT_CSS = """
    PromptModal {
        align: center middle;
    }
    #dialog {
        width: 60;
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
        placeholder: str = "",
        initial: str = "",
        confirm_label: str = "Aceptar",
        allow_empty: bool = False,
    ) -> None:
        super().__init__()
        self._title = title
        self._placeholder = placeholder
        self._initial = initial
        self._confirm_label = confirm_label
        self._allow_empty = allow_empty

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._title, id="title")
            yield Input(
                value=self._initial, placeholder=self._placeholder, id="prompt-input"
            )
            with Horizontal(id="buttons"):
                yield Button("Cancelar", id="cancel")
                yield Button(
                    self._confirm_label,
                    id="confirm",
                    variant="primary",
                    disabled=not (self._allow_empty or bool(self._initial)),
                )

    def on_mount(self) -> None:
        inp = self.query_one("#prompt-input", Input)
        inp.focus()
        if inp.value:
            inp.cursor_position = len(inp.value)

    @on(Input.Changed, "#prompt-input")
    def _on_change(self, event: Input.Changed) -> None:
        self.query_one("#confirm", Button).disabled = not (
            self._allow_empty or bool(event.value.strip())
        )

    @on(Input.Submitted, "#prompt-input")
    def _on_submit(self, event: Input.Submitted) -> None:
        self._submit()

    @on(Button.Pressed, "#confirm")
    def _on_confirm(self) -> None:
        self._submit()

    @on(Button.Pressed, "#cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        value = self.query_one("#prompt-input", Input).value
        if not self._allow_empty and not value.strip():
            return
        self.dismiss(value.strip())


class PaneEditModal(ModalScreen[Pane | None]):
    """Edita las propiedades de un Pane (hoja o contenedor).

    Devuelve un nuevo Pane con los cambios o None si se cancela.
    El pane original no se muta: el caller decide como aplicarlo.
    """

    BINDINGS = [Binding("escape", "dismiss_none", "Cancelar")]

    DEFAULT_CSS = """
    PaneEditModal {
        align: center middle;
    }
    #dialog {
        width: 80;
        height: auto;
        max-height: 90%;
        border: round $accent;
        padding: 1 2;
        background: $surface;
    }
    #title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    .row {
        height: 3;
        margin-bottom: 0;
    }
    .label {
        width: 20;
        color: $text-muted;
        padding-top: 1;
    }
    .narrow {
        width: 30;
    }
    Input {
        width: 1fr;
    }
    Switch {
        width: auto;
    }
    RadioSet {
        width: 1fr;
        height: 3;
        layout: horizontal;
    }
    #buttons {
        align-horizontal: right;
        height: 3;
        margin-top: 1;
    }
    Button {
        margin-left: 1;
    }
    """

    def __init__(self, pane: Pane) -> None:
        super().__init__()
        self._pane = pane
        self._is_container = pane.is_container

    def compose(self) -> ComposeResult:
        kind = "contenedor" if self._is_container else "hoja"
        with Vertical(id="dialog"):
            yield Static(f"Editar pane ({kind})", id="title")

            with Horizontal(classes="row"):
                yield Static("Nombre", classes="label")
                yield Input(value=self._pane.name or "", id="name", placeholder="opcional")

            with Horizontal(classes="row"):
                yield Static("Size", classes="label")
                yield Input(
                    value=self._pane.size or "",
                    id="size",
                    placeholder="ej. 60% o 1",
                )

            with Horizontal(classes="row"):
                yield Static("Focus", classes="label")
                yield Switch(value=self._pane.focus, id="focus")

            if self._is_container:
                with Horizontal(classes="row"):
                    yield Static("Split direction", classes="label")
                    with RadioSet(id="split"):
                        yield RadioButton(
                            "vertical",
                            value=self._pane.split_direction == "vertical",
                        )
                        yield RadioButton(
                            "horizontal",
                            value=self._pane.split_direction == "horizontal",
                        )
                        yield RadioButton(
                            "(none)",
                            value=self._pane.split_direction is None,
                        )
            else:
                with Horizontal(classes="row"):
                    yield Static("Comando", classes="label")
                    yield Input(
                        value=self._pane.command or "",
                        id="command",
                        placeholder="ej. nvim",
                    )
                with Horizontal(classes="row"):
                    yield Static("Args", classes="label")
                    yield Input(
                        value=shlex.join(self._pane.args) if self._pane.args else "",
                        id="args",
                        placeholder="ej. --verbose --file foo.txt",
                    )
                with Horizontal(classes="row"):
                    yield Static("CWD", classes="label")
                    yield Input(
                        value=self._pane.cwd or "",
                        id="cwd",
                        placeholder="opcional, ej. /home/martin/proj",
                    )
                with Horizontal(classes="row"):
                    yield Static("Start suspended", classes="label")
                    yield Switch(
                        value=self._pane.start_suspended, id="start_suspended"
                    )
                with Horizontal(classes="row"):
                    yield Static("Borderless", classes="label")
                    yield Switch(value=self._pane.borderless, id="borderless")

            with Horizontal(id="buttons"):
                yield Button("Cancelar", id="cancel")
                yield Button("Guardar", id="save", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#name", Input).focus()

    @on(Button.Pressed, "#cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#save")
    def _on_save(self) -> None:
        self._submit()

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        new_pane = Pane(
            children=list(self._pane.children),
            raw_unknown_nodes=list(self._pane.raw_unknown_nodes),
        )
        new_pane.name = _none_if_empty(self.query_one("#name", Input).value)
        new_pane.size = _none_if_empty(self.query_one("#size", Input).value)
        new_pane.focus = self.query_one("#focus", Switch).value

        if self._is_container:
            split_set = self.query_one("#split", RadioSet)
            choice: SplitDirection | None = None
            if split_set.pressed_button is not None:
                label = str(split_set.pressed_button.label).strip()
                if label in ("vertical", "horizontal"):
                    choice = label  # type: ignore[assignment]
            new_pane.split_direction = choice
        else:
            new_pane.command = _none_if_empty(self.query_one("#command", Input).value)
            args_value = self.query_one("#args", Input).value.strip()
            new_pane.args = shlex.split(args_value) if args_value else []
            new_pane.cwd = _none_if_empty(self.query_one("#cwd", Input).value)
            new_pane.start_suspended = self.query_one("#start_suspended", Switch).value
            new_pane.borderless = self.query_one("#borderless", Switch).value
            new_pane.split_direction = None
        self.dismiss(new_pane)


def _none_if_empty(value: str) -> str | None:
    value = value.strip()
    return value if value else None


class EditColorModal(ModalScreen[str | None]):
    """Modal para editar un valor de color hex con validacion en vivo."""

    BINDINGS = [Binding("escape", "dismiss_none", "Cancelar")]

    DEFAULT_CSS = """
    EditColorModal {
        align: center middle;
    }
    #dialog {
        width: 60;
        height: auto;
        border: round $accent;
        padding: 1 2;
        background: $surface;
    }
    #title {
        text-style: bold;
        color: $accent;
    }
    .label {
        color: $text-muted;
    }
    #swatch {
        height: 3;
        margin: 1 0;
        content-align: center middle;
    }
    #status {
        color: $text-muted;
    }
    #buttons {
        align-horizontal: right;
        height: 3;
        margin-top: 1;
    }
    Button {
        margin-left: 1;
    }
    """

    def __init__(
        self,
        *,
        slot_label: str,
        initial: str = "",
    ) -> None:
        super().__init__()
        self._slot_label = slot_label
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(f"Editar {self._slot_label}", id="title")
            yield Static("Hex: #rgb, #rrggbb o #rrggbbaa", classes="label")
            yield Input(
                value=self._initial,
                placeholder="#1e1e2e",
                id="hex-input",
            )
            yield Static("", id="swatch")
            yield Static("", id="status")
            with Horizontal(id="buttons"):
                yield Button("Cancelar", id="cancel")
                yield Button("Guardar", id="save", variant="primary", disabled=True)

    def on_mount(self) -> None:
        inp = self.query_one("#hex-input", Input)
        inp.focus()
        inp.cursor_position = len(inp.value)
        self._refresh()

    @on(Input.Changed, "#hex-input")
    def _on_change(self) -> None:
        self._refresh()

    @on(Input.Submitted, "#hex-input")
    def _on_submit(self) -> None:
        self._submit()

    @on(Button.Pressed, "#save")
    def _on_save(self) -> None:
        self._submit()

    @on(Button.Pressed, "#cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def _refresh(self) -> None:
        from zellij_themes.colors import is_valid_hex, normalize_hex

        value = self.query_one("#hex-input", Input).value.strip()
        valid = is_valid_hex(value)
        self.query_one("#save", Button).disabled = not valid
        swatch = self.query_one("#swatch", Static)
        status = self.query_one("#status", Static)
        if valid:
            normalized = normalize_hex(value)
            swatch.update(f"[on {normalized}]                              [/]")
            status.update(f"OK  ->  {normalized}")
        else:
            swatch.update("")
            status.update("Formato invalido")

    def _submit(self) -> None:
        from zellij_themes.colors import is_valid_hex, normalize_hex

        value = self.query_one("#hex-input", Input).value.strip()
        if not is_valid_hex(value):
            return
        self.dismiss(normalize_hex(value))


