from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Literal

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    OptionList,
    RadioButton,
    RadioSet,
    Static,
    Switch,
)

from ztc.models.layout import Pane, SplitDirection

UnsavedChangesChoice = Literal["cancel", "discard", "save"]


@dataclass(frozen=True)
class KittyRemoteControlChoice:
    action: Literal["enable", "skip"]
    dont_show_again: bool = False


# Estilo "chip" plano para todos los Buttons de la app: sin el shadow de
# media-blocks que usa Button por default; border ASCII round que hace
# juego con el resto de la UI. Cada App (TermConfigApp / SessionLauncherApp)
# concatena este string a su `DEFAULT_CSS`.
BUTTON_CSS = """
/* `!important` necesario porque `Button.-style-default` (definido en
   Button.DEFAULT_CSS de Textual) tiene mayor specificity que `Screen
   Button`. Textual soporta `!important` (el propio Button.DEFAULT_CSS
   lo usa para overrides internos). Sin el flag, las reglas de Textual
   ganan y los botones siguen viendose con shadow de media-blocks. */
Button {
    border: round $panel !important;
    background: transparent !important;
    color: $foreground !important;
    min-width: 12;
    padding: 0 1;
    height: 3;
    margin-left: 1;
}
Button:hover {
    background: $boost !important;
    border: round $panel !important;
}
Button:focus {
    border: round $accent !important;
}
Button.-primary {
    border: round $primary !important;
    background: transparent !important;
    color: $primary !important;
    text-style: bold;
}
Button.-primary:hover {
    background: $primary 20% !important;
    border: round $primary !important;
}
Button.-success {
    border: round $success !important;
    background: transparent !important;
    color: $success !important;
    text-style: bold;
}
Button.-success:hover {
    background: $success 20% !important;
    border: round $success !important;
}
Button.-error {
    border: round $error !important;
    background: transparent !important;
    color: $error !important;
    text-style: bold;
}
Button.-error:hover {
    background: $error 20% !important;
    border: round $error !important;
}
Button.-warning {
    border: round $warning !important;
    background: transparent !important;
    color: $warning !important;
    text-style: bold;
}
Button.-warning:hover {
    background: $warning 20% !important;
    border: round $warning !important;
}
"""


class ConfirmActionModal(ModalScreen[bool]):
    """Modal simple para confirmar acciones destructivas con No/Yes.

    El foco inicial queda en No para que Enter no confirme por accidente.
    """

    BINDINGS = [
        Binding("escape", "dismiss_false", "Cancel"),
    ]

    DEFAULT_CSS = """
    ConfirmActionModal {
        align: center middle;
    }
    #dialog {
        width: 60;
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
                yield Button("No", id="cancel", variant="default")
                yield Button(self._confirm_label, id="confirm", variant="error")

    def on_mount(self) -> None:
        self.query_one("#cancel", Button).focus()

    @on(Button.Pressed, "#confirm")
    def _on_confirm_action(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def _on_cancel_action(self) -> None:
        self.dismiss(False)

    def action_dismiss_false(self) -> None:
        self.dismiss(False)


class PromptModal(ModalScreen[str | None]):
    """Modal generico de un solo input: pide texto, devuelve string o None si cancela."""

    BINDINGS = [Binding("escape", "dismiss_none", "Cancel")]

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
    """

    def __init__(
        self,
        *,
        title: str,
        placeholder: str = "",
        initial: str = "",
        confirm_label: str = "OK",
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
                yield Button("Cancel", id="cancel")
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

    BINDINGS = [Binding("escape", "dismiss_none", "Cancel")]

    DEFAULT_CSS = """
    PaneEditModal {
        align: center middle;
    }
    #dialog {
        width: 70;
        height: 90%;
        border: round $accent;
        padding: 1 2;
        background: $surface;
        layout: vertical;
    }
    #title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
        height: 1;
    }
    #form {
        width: 100%;
        height: 1fr;
    }
    .row {
        width: 100%;
        height: 3;
        margin-bottom: 0;
    }
    .label {
        width: 20;
        color: $text-muted;
        padding-top: 1;
    }
    Input {
        width: 1fr;
    }
    Switch {
        width: auto;
    }
    .field {
        width: 1fr;
        height: 3;
        layout: horizontal;
    }
    .color-field {
        padding-right: 3;
    }
    .color-preview {
        dock: right;
        width: 2;
        height: 1;
        margin-top: 1;
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
    """

    def __init__(self, pane: Pane) -> None:
        super().__init__()
        self._pane = pane
        self._is_container = pane.is_container

    def compose(self) -> ComposeResult:
        from textual.containers import VerticalScroll

        kind = "container" if self._is_container else "leaf"
        with Vertical(id="dialog"):
            yield Static(f"Edit pane ({kind})", id="title")

            with VerticalScroll(id="form"):
                with Horizontal(classes="row"):
                    yield Static("Name", classes="label")
                    with Horizontal(classes="field"):
                        yield Input(
                            value=self._pane.name or "",
                            id="name",
                            placeholder="optional",
                        )

                with Horizontal(classes="row"):
                    yield Static("Size", classes="label")
                    with Horizontal(classes="field"):
                        yield Input(
                            value=self._pane.size or "",
                            id="size",
                            placeholder="e.g. 60%",
                        )

                if self._is_container:
                    with Horizontal(classes="row"):
                        yield Static("Split direction", classes="label")
                        with Horizontal(classes="field"), RadioSet(id="split"):
                            yield RadioButton(
                                "vert.",
                                value=self._pane.split_direction == "vertical",
                                id="dir-vertical",
                            )
                            yield RadioButton(
                                "horiz.",
                                value=self._pane.split_direction == "horizontal",
                                id="dir-horizontal",
                            )
                            yield RadioButton(
                                "(none)",
                                value=self._pane.split_direction is None,
                                id="dir-none",
                            )
                else:
                    with Horizontal(classes="row"):
                        yield Static("Focus", classes="label")
                        with Horizontal(classes="field"):
                            yield Switch(value=self._pane.focus, id="focus")

                    with Horizontal(classes="row"):
                        yield Static("Default bg", classes="label")
                        with Horizontal(classes="field color-field"):
                            yield Input(
                                value=self._pane.default_bg or "",
                                id="default_bg",
                                placeholder="#rrggbb / rgb:rr/gg/bb",
                            )
                            yield Static(
                                "  ",
                                id="default_bg-preview",
                                classes="color-preview",
                            )
                    with Horizontal(classes="row"):
                        yield Static("Default fg", classes="label")
                        with Horizontal(classes="field color-field"):
                            yield Input(
                                value=self._pane.default_fg or "",
                                id="default_fg",
                                placeholder="#rrggbb / rgb:rr/gg/bb",
                            )
                            yield Static(
                                "  ",
                                id="default_fg-preview",
                                classes="color-preview",
                            )

                    with Horizontal(classes="row"):
                        yield Static("Command", classes="label")
                        with Horizontal(classes="field"):
                            yield Input(
                                value=self._pane.command or "",
                                id="command",
                                placeholder="e.g. nvim",
                            )
                    with Horizontal(classes="row"):
                        yield Static("Args", classes="label")
                        with Horizontal(classes="field"):
                            yield Input(
                                value=(
                                    shlex.join(self._pane.args)
                                    if self._pane.args
                                    else ""
                                ),
                                id="args",
                                placeholder="e.g. --verbose --file foo.txt",
                            )
                    with Horizontal(classes="row"):
                        yield Static("CWD", classes="label")
                        with Horizontal(classes="field"):
                            yield Input(
                                value=self._pane.cwd or "",
                                id="cwd",
                                placeholder="optional, e.g. /home/martin/proj",
                            )
                    with Horizontal(classes="row"):
                        yield Static("Start suspended", classes="label")
                        with Horizontal(classes="field"):
                            yield Switch(
                                value=self._pane.start_suspended,
                                id="start_suspended",
                            )
                    with Horizontal(classes="row"):
                        yield Static("Borderless", classes="label")
                        with Horizontal(classes="field"):
                            yield Switch(value=self._pane.borderless, id="borderless")

            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Apply", id="save", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#name", Input).focus()
        if not self._is_container:
            # Preview inicial reflejando el valor del modelo (si trae color).
            self._refresh_color_preview("default_bg")
            self._refresh_color_preview("default_fg")

    @on(Button.Pressed, "#cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#save")
    def _on_save(self) -> None:
        self._submit()

    @on(Input.Changed, "#default_bg")
    def _on_default_bg_changed(self) -> None:
        self._refresh_color_preview("default_bg")

    @on(Input.Changed, "#default_fg")
    def _on_default_fg_changed(self) -> None:
        self._refresh_color_preview("default_fg")

    def _refresh_color_preview(self, field_id: str) -> None:
        """Actualiza el bloque de color al lado del Input segun el valor
        actual. Si el valor es invalido o vacio, limpia el preview."""
        from ztc.services.colors import zellij_color_to_rich_hex

        value = self.query_one(f"#{field_id}", Input).value.strip()
        preview = self.query_one(f"#{field_id}-preview", Static)
        rich_hex = zellij_color_to_rich_hex(value) if value else None
        if rich_hex is None:
            preview.update("  ")
        else:
            preview.update(f"[on {rich_hex}]  [/]")

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        from ztc.services.colors import is_valid_zellij_pane_color

        bg_input = ""
        fg_input = ""
        size_input = self.query_one("#size", Input).value.strip()

        # Validacion estricta: campo vacio = unset; valor no vacio
        # debe matchear los formatos aceptados por Zellij. Si invalido,
        # notify y mantener modal abierto.
        from ztc.zellij.layout_ops import is_valid_pane_size

        if size_input and not is_valid_pane_size(size_input):
            self.app.notify(
                f"Invalid Size: {size_input!r}. Expected a percentage "
                "from 1% to 100% without quotes.",
                severity="error",
                timeout=6,
            )
            return
        if not self._is_container:
            bg_input = self.query_one("#default_bg", Input).value.strip()
            fg_input = self.query_one("#default_fg", Input).value.strip()
            if bg_input and not is_valid_zellij_pane_color(bg_input):
                self.app.notify(
                    f"Invalid Default bg: {bg_input!r}. "
                    "Expected #rgb, #rrggbb, #rrggbbaa, or rgb:rr/gg/bb.",
                    severity="error",
                    timeout=6,
                )
                return
            if fg_input and not is_valid_zellij_pane_color(fg_input):
                self.app.notify(
                    f"Invalid Default fg: {fg_input!r}. "
                    "Expected #rgb, #rrggbb, #rrggbbaa, or rgb:rr/gg/bb.",
                    severity="error",
                    timeout=6,
                )
                return

        new_pane = Pane(
            children=list(self._pane.children),
            raw_unknown_nodes=list(self._pane.raw_unknown_nodes),
        )
        new_pane.name = _none_if_empty(self.query_one("#name", Input).value)
        new_pane.size = size_input or None

        if self._is_container:
            split_set = self.query_one("#split", RadioSet)
            choice: SplitDirection | None = None
            pressed = split_set.pressed_button
            if pressed is not None:
                if pressed.id == "dir-vertical":
                    choice = "vertical"
                elif pressed.id == "dir-horizontal":
                    choice = "horizontal"
            new_pane.split_direction = choice
        else:
            new_pane.focus = self.query_one("#focus", Switch).value
            new_pane.default_bg = bg_input or None
            new_pane.default_fg = fg_input or None
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

    BINDINGS = [Binding("escape", "dismiss_none", "Cancel")]

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
        margin-bottom: 1;
    }
    .label {
        color: $text-muted;
    }
    #swatch {
        height: 3;
        margin: 1 0;
        content-align: center middle;
    }
    #buttons {
        align-horizontal: right;
        height: 3;
        margin-top: 1;
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
            yield Static(f"Edit {self._slot_label}", id="title")
            yield Input(
                value=self._initial,
                placeholder="#1e1e2e",
                id="hex-input",
            )
            yield Static("", id="swatch")
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Apply", id="save", variant="primary", disabled=True)

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
        from ztc.services.colors import is_valid_hex, normalize_hex

        value = self.query_one("#hex-input", Input).value.strip()
        valid = is_valid_hex(value)
        self.query_one("#save", Button).disabled = not valid
        swatch = self.query_one("#swatch", Static)
        if valid:
            normalized = normalize_hex(value)
            swatch.update(f"[on {normalized}]                              [/]")
        else:
            swatch.update(
                "[bold red on white]        Invalid format        [/]"
            )

    def _submit(self) -> None:
        from ztc.services.colors import is_valid_hex, normalize_hex

        value = self.query_one("#hex-input", Input).value.strip()
        if not is_valid_hex(value):
            return
        self.dismiss(normalize_hex(value))


class UnsavedChangesModal(ModalScreen["UnsavedChangesChoice"]):
    """Modal de salida con cambios pending. 3 botones, sin escribir nada:
    - **Cancel** (Esc): vuelve al editor.
    - **Discard**: descarta cambios y sale.
    - **Save** (success): guarda y sale (el caller invoca `action_save`).

    Devuelve `"cancel"` / `"discard"` / `"save"`. El caller maneja los 3
    casos — si el save falla, el caller deberia mostrar un toast y no
    salir (queda en el editor con el dirty intacto).
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    UnsavedChangesModal {
        align: center middle;
    }
    #dialog {
        width: 60;
        height: auto;
        border: round $warning;
        padding: 1 2;
        background: $surface;
    }
    #title {
        text-style: bold;
        color: $warning;
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
        title: str = "Unsaved changes",
        message: str = (
            "You have unsaved changes. What do you want to do?"
        ),
    ) -> None:
        super().__init__()
        self._title = title
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._title, id="title")
            yield Static(self._message, id="message")
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Discard", id="discard", variant="error")
                yield Button("Save", id="save", variant="success")

    def on_mount(self) -> None:
        # Foco en Cancel por seguridad: enter accidental no descarta.
        self.query_one("#cancel", Button).focus()

    @on(Button.Pressed, "#cancel")
    def _on_cancel(self) -> None:
        self.dismiss("cancel")

    @on(Button.Pressed, "#discard")
    def _on_discard(self) -> None:
        self.dismiss("discard")

    @on(Button.Pressed, "#save")
    def _on_save(self) -> None:
        self.dismiss("save")

    def action_cancel(self) -> None:
        self.dismiss("cancel")


class KittyRemoteControlModal(ModalScreen[KittyRemoteControlChoice | None]):
    """Modal para habilitar auto-reload de Kitty."""

    BINDINGS = [Binding("escape", "dismiss_none", "Cancel")]

    DEFAULT_CSS = """
    KittyRemoteControlModal {
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
    #message {
        margin-bottom: 1;
    }
    #footer {
        width: 100%;
        height: 3;
        layout: horizontal;
    }
    #remember {
        width: 1fr;
        height: 3;
    }
    #buttons {
        width: auto;
        align-horizontal: right;
        height: 3;
    }
    """

    def __init__(
        self,
        *,
        inside_zellij: bool = False,
        remote_control_missing: bool = True,
        listen_on_missing: bool | None = None,
        dynamic_background_opacity_missing: bool = False,
    ) -> None:
        super().__init__()
        self._inside_zellij = inside_zellij
        self._remote_control_missing = remote_control_missing
        self._listen_on_missing = (
            inside_zellij if listen_on_missing is None else listen_on_missing
        )
        self._dynamic_background_opacity_missing = (
            dynamic_background_opacity_missing
        )

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Auto-reload not configured in Kitty", id="title")
            yield Static(self._message(), id="message")
            with Horizontal(id="footer"):
                yield Checkbox("Don't ask again", id="remember")
                with Horizontal(id="buttons"):
                    yield Button("Yes", id="enable", variant="success")
                    yield Button("No", id="skip")

    def _message(self) -> str:
        parts = [
            "ZTC can automatically refresh your terminal whenever you "
            "change colors, settings, or Zellij themes. "
        ]
        missing: list[str] = []
        if self._remote_control_missing:
            missing.append("allow_remote_control yes")
        if self._listen_on_missing:
            missing.append("listen_on unix:@ztc-{kitty_pid}")
        if self._dynamic_background_opacity_missing:
            missing.append("dynamic_background_opacity yes")

        if self._inside_zellij and self._listen_on_missing:
            parts.append(
                "Because ZTC is running inside Zellij, Kitty also needs a "
                "listener socket so the reload command can reach the parent "
                "Kitty process. "
            )
        if self._dynamic_background_opacity_missing:
            parts.append(
                "Live background opacity changes require Kitty to start with "
                "dynamic background opacity enabled. "
            )
        parts.append(
            "Missing setting(s): "
            + ", ".join(missing)
            + ". Without them, some changes will require a manual reload "
            "with Ctrl + Shift + F5 or a Kitty restart. Would you like ZTC "
            "to add only the missing setting(s) to kitty.conf? If you choose "
            "Yes, restart Kitty once for the new settings to take effect."
        )
        return "".join(parts)

    def on_mount(self) -> None:
        self.query_one("#skip", Button).focus()

    @on(Button.Pressed, "#enable")
    def _on_enable(self) -> None:
        self.dismiss(KittyRemoteControlChoice(action="enable"))

    @on(Button.Pressed, "#skip")
    def _on_skip(self) -> None:
        remember = self.query_one("#remember", Checkbox).value
        self.dismiss(
            KittyRemoteControlChoice(
                action="skip",
                dont_show_again=remember,
            )
        )

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


class KdlPreviewModal(ModalScreen[None]):
    """Modal de solo lectura que muestra contenido KDL con scroll.
    Util para previsualizar el archivo de layout antes de guardar.
    """

    BINDINGS = [
        Binding("escape", "dismiss_none", "Close"),
        Binding("q", "noop", show=False),
        Binding("ctrl+q", "noop", show=False),
    ]

    DEFAULT_CSS = """
    KdlPreviewModal {
        align: center middle;
    }
    #dialog {
        width: 80%;
        height: 80%;
        border: round $accent;
        padding: 1 2;
        background: $surface;
    }
    #title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
        height: 1;
    }
    #scroller {
        height: 1fr;
        border: solid $panel;
    }
    #content {
        padding: 0 1;
    }
    #buttons {
        align-horizontal: right;
        height: 3;
        margin-top: 1;
    }
    """

    def __init__(self, *, title: str, content: str) -> None:
        super().__init__()
        self._title = title
        self._content = content

    def compose(self) -> ComposeResult:
        from textual.containers import VerticalScroll

        with Vertical(id="dialog"):
            yield Static(self._title, id="title")
            with VerticalScroll(id="scroller"):
                yield Static(self._content, id="content")
            with Horizontal(id="buttons"):
                yield Button("Close", id="close", variant="primary")

    @on(Button.Pressed, "#close")
    def _on_close(self) -> None:
        self.dismiss(None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def action_noop(self) -> None:
        pass


class FontPickerModal(ModalScreen[str | None]):
    """Modal para elegir una fuente de una lista (e.g. monoespaciadas
    detectadas en el sistema). Devuelve el nombre elegido o None si
    cancela. Escalable: usa OptionList con scroll para listas largas.
    Si la fuente actual esta en `choices`, la pre-selecciona.
    """

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel"),
        Binding("enter", "confirm", "OK", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    FontPickerModal {
        align: center middle;
    }
    #dialog {
        width: 60;
        height: 24;
        border: round $accent;
        padding: 1 2;
        background: $surface;
    }
    #title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
        height: 1;
    }
    OptionList {
        height: 1fr;
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
        choices: list[str],
        initial: str | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._choices = choices
        self._initial = initial

    def compose(self) -> ComposeResult:
        from textual.widgets.option_list import Option

        with Vertical(id="dialog"):
            yield Static(self._title, id="title")
            ol = OptionList(
                *[Option(name, id=name) for name in self._choices],
                id="font-list",
            )
            yield ol
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("OK", id="confirm", variant="primary")

    def on_mount(self) -> None:
        ol = self.query_one("#font-list", OptionList)
        ol.focus()
        if self._initial is not None:
            for i in range(ol.option_count):
                opt = ol.get_option_at_index(i)
                if opt.id == self._initial:
                    ol.highlighted = i
                    break

    def _selected(self) -> str | None:
        ol = self.query_one("#font-list", OptionList)
        if ol.highlighted is None:
            return None
        return ol.get_option_at_index(ol.highlighted).id

    def _confirm_selected(self) -> None:
        self.dismiss(self._selected())

    @on(OptionList.OptionSelected, "#font-list")
    def _on_font_selected(self) -> None:
        self._confirm_selected()

    @on(Button.Pressed, "#cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm")
    def _on_confirm(self) -> None:
        self._confirm_selected()

    def action_confirm(self) -> None:
        self._confirm_selected()

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


class EnumPickerModal(ModalScreen[str | None]):
    """Modal para elegir un valor de un enum cerrado (RadioSet).
    Devuelve el string elegido o None si cancela.
    """

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel"),
        Binding("enter", "confirm", "OK", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    EnumPickerModal {
        align: center middle;
    }
    #dialog {
        width: 50;
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
    RadioSet {
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
        choices: tuple[str, ...],
        initial: str | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._choices = choices
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self._title, id="title")
            with RadioSet(id="enum-choices"):
                for choice in self._choices:
                    yield RadioButton(
                        choice,
                        value=(choice == self._initial),
                        id=f"choice-{choice}",
                    )
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("OK", id="confirm", variant="primary")

    def on_mount(self) -> None:
        rs = self.query_one("#enum-choices", RadioSet)
        if rs.pressed_index >= 0:
            rs._selected = rs.pressed_index
        rs.focus()

    @on(Button.Pressed, "#cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm")
    def _on_confirm(self) -> None:
        self.action_confirm()

    def action_confirm(self) -> None:
        rs = self.query_one("#enum-choices", RadioSet)
        button = self._selected_button(rs) or rs.pressed_button
        if button is None:
            return
        # El id del RadioButton es "choice-<value>"; extraemos value.
        prefix = "choice-"
        button_id = button.id or ""
        if button_id.startswith(prefix):
            self.dismiss(button_id[len(prefix):])
        else:
            self.dismiss(None)

    def _selected_button(self, rs: RadioSet) -> RadioButton | None:
        selected = getattr(rs, "_selected", None)
        buttons = list(rs.query(RadioButton))
        if isinstance(selected, int) and 0 <= selected < len(buttons):
            return buttons[selected]
        return None

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
