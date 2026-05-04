from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from term_config_tui.models.theme import ZellijColor, ZellijTheme
from term_config_tui.services import theme_sync, zellij_config, zellij_themes
from term_config_tui.widgets.confirm import (
    ConfirmByNameModal,
    EditColorModal,
)

_LEGACY_PREFIX = "legacy:"
_RICH_PREFIX = "rich:"
_HEADER_PREFIX = "header:"


class CustomThemeEditorScreen(Screen[None]):
    """Edita los slots de un user theme: paleta legacy + slots ricos."""

    BINDINGS = [
        Binding("enter", "edit", "Editar slot"),
        Binding("x", "reset", "Resetear slot"),
        Binding("s", "save", "Guardar"),
        Binding("escape", "back", "Volver"),
        Binding("q", "back", "Volver", show=False),
    ]

    DEFAULT_CSS = """
    CustomThemeEditorScreen {
        layout: vertical;
    }
    #header-info {
        padding: 0 1;
        height: 1;
    }
    #body {
        height: 1fr;
    }
    OptionList {
        width: 60;
        border-right: solid $panel;
    }
    #detail {
        padding: 1 2;
        height: 1fr;
    }
    #detail-name {
        text-style: bold;
        color: $accent;
    }
    #big-swatch {
        height: 5;
        margin: 1 0;
    }
    """

    def __init__(self, config_path: Path, theme: ZellijTheme) -> None:
        super().__init__()
        self.config_path = config_path
        self.theme = ZellijTheme(
            name=theme.name,
            source="user",
            colors=list(theme.colors),
            raw_components=list(theme.raw_components),
        )
        self.dirty = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="header-info")
        with Horizontal(id="body"):
            yield OptionList(id="slot-list")
            with Vertical(id="detail"):
                yield Static("", id="detail-name")
                yield Static("", id="big-swatch")
                yield Static("", id="detail-meta")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_header()
        self._rebuild_list()

    # ---------- helpers ----------

    def _refresh_header(self) -> None:
        dirty = " *" if self.dirty else ""
        self.query_one("#header-info", Static).update(
            f"[b]theme: {self.theme.name}[/b]{dirty}    {self.config_path}"
        )

    def _legacy_slot_names(self) -> list[str]:
        defined = {c.name for c in self.theme.colors}
        ordered = list(zellij_themes.LEGACY_SLOTS)
        for name in defined:
            if name not in ordered:
                ordered.append(name)
        return ordered

    def _legacy_value(self, slot: str) -> str | None:
        for c in self.theme.colors:
            if c.name == slot:
                return c.value
        return None

    def _rich_value(self, component: str, slot: str) -> str | None:
        return zellij_themes.get_rich_slot(self.theme, component, slot)

    def _rebuild_list(self) -> None:
        option_list = self.query_one("#slot-list", OptionList)
        prev = option_list.highlighted
        option_list.clear_options()

        # Header de seccion legacy
        option_list.add_option(
            Option("── Paleta ANSI ──", id=_HEADER_PREFIX + "ansi", disabled=True)
        )
        for slot in self._legacy_slot_names():
            value = self._legacy_value(slot) or "(sin definir)"
            option_list.add_option(
                Option(self._format_row(slot, value), id=_LEGACY_PREFIX + slot)
            )

        # Header de seccion rich
        option_list.add_option(
            Option("── UI (Zellij) ──", id=_HEADER_PREFIX + "ui", disabled=True)
        )
        for component, slot in zellij_themes.RICH_SLOTS_TO_EXPOSE:
            value = self._rich_value(component, slot) or "(sin definir)"
            label = self._format_row(zellij_themes.display_slot(component, slot), value)
            option_list.add_option(
                Option(label, id=f"{_RICH_PREFIX}{component}.{slot}")
            )

        if option_list.option_count:
            # Saltar el header inicial: si prev no aplica, ir al primer slot real (idx 1).
            if prev is None or prev >= option_list.option_count:
                option_list.highlighted = 1
            else:
                option_list.highlighted = prev
            self._show_detail_at(option_list.highlighted)

    def _format_row(self, label: str, value: str) -> str:
        swatch = f"[on {value}]      [/]" if value.startswith("#") else "      "
        return f"{label:<26} {value:<10} {swatch}"

    def _slot_at(self, index: int) -> tuple[str, str | None] | None:
        """Devuelve ('legacy', slot) o ('rich', 'component.slot') segun
        el option en el indice. None si es header u out of bounds."""
        option_list = self.query_one("#slot-list", OptionList)
        if index is None or not 0 <= index < option_list.option_count:
            return None
        opt = option_list.get_option_at_index(index)
        if opt.id is None or opt.id.startswith(_HEADER_PREFIX):
            return None
        if opt.id.startswith(_LEGACY_PREFIX):
            return ("legacy", opt.id[len(_LEGACY_PREFIX):])
        if opt.id.startswith(_RICH_PREFIX):
            return ("rich", opt.id[len(_RICH_PREFIX):])
        return None

    def _show_detail_at(self, index: int | None) -> None:
        if index is None:
            return
        slot_info = self._slot_at(index)
        name_widget = self.query_one("#detail-name", Static)
        swatch_widget = self.query_one("#big-swatch", Static)
        meta_widget = self.query_one("#detail-meta", Static)

        if slot_info is None:
            name_widget.update("(seleccion)")
            swatch_widget.update("")
            meta_widget.update("Mueve para elegir un slot.")
            return

        kind, slot_id = slot_info
        if kind == "legacy":
            value = self._legacy_value(slot_id)
            display_name = slot_id
        else:
            component, slot = slot_id.split(".", 1)
            value = self._rich_value(component, slot)
            display_name = zellij_themes.display_slot(component, slot)

        name_widget.update(display_name)
        if value and value.startswith("#"):
            big = "\n".join(
                [f"[on {value}]                                                  [/]"] * 3
            )
            swatch_widget.update(big)
            meta_widget.update(
                f"Valor actual: {value}\nEnter para editar / x para resetear."
            )
        else:
            swatch_widget.update("")
            meta_widget.update(
                f"Valor actual: {value or '(sin definir)'}\nEnter para definir."
            )

    @on(OptionList.OptionHighlighted, "#slot-list")
    def _on_highlight(self, event: OptionList.OptionHighlighted) -> None:
        self._show_detail_at(self.query_one("#slot-list", OptionList).highlighted)

    @on(OptionList.OptionSelected, "#slot-list")
    def _on_select(self) -> None:
        self.action_edit()

    # ---------- acciones ----------

    def action_edit(self) -> None:
        option_list = self.query_one("#slot-list", OptionList)
        slot_info = self._slot_at(option_list.highlighted)
        if slot_info is None:
            return
        kind, slot_id = slot_info

        if kind == "legacy":
            slot = slot_id
            current = self._legacy_value(slot) or ""
            label = f"{self.theme.name}.{slot}"

            def after_legacy(value: str | None) -> None:
                if value is None:
                    return
                for i, c in enumerate(self.theme.colors):
                    if c.name == slot:
                        self.theme.colors[i] = ZellijColor(name=slot, value=value)
                        break
                else:
                    self.theme.colors.append(ZellijColor(name=slot, value=value))
                self.dirty = True
                self._refresh_header()
                self._rebuild_list()

            self.app.push_screen(
                EditColorModal(slot_label=label, initial=current),
                after_legacy,
            )
        else:
            component, slot = slot_id.split(".", 1)
            current = self._rich_value(component, slot) or ""
            label = f"{self.theme.name}.{component}.{slot}"

            def after_rich(value: str | None) -> None:
                if value is None:
                    return
                zellij_themes.set_rich_slot(self.theme, component, slot, value)
                self.dirty = True
                self._refresh_header()
                self._rebuild_list()

            self.app.push_screen(
                EditColorModal(slot_label=label, initial=current),
                after_rich,
            )

    def action_reset(self) -> None:
        option_list = self.query_one("#slot-list", OptionList)
        slot_info = self._slot_at(option_list.highlighted)
        if slot_info is None:
            return
        kind, slot_id = slot_info

        if kind == "legacy":
            slot = slot_id
            before = len(self.theme.colors)
            self.theme.colors = [c for c in self.theme.colors if c.name != slot]
            if len(self.theme.colors) == before:
                self.app.notify(
                    f"{slot} ya estaba sin definir", severity="information"
                )
                return
            self.dirty = True
        else:
            component, slot = slot_id.split(".", 1)
            if self._rich_value(component, slot) is None:
                self.app.notify(
                    f"{component}.{slot} ya estaba sin definir",
                    severity="information",
                )
                return
            zellij_themes.unset_rich_slot(self.theme, component, slot)
            self.dirty = True

        self._refresh_header()
        self._rebuild_list()
        self.app.notify(
            "Slot reseteado (pulsa 's' para guardar al disco)",
            severity="information",
            timeout=5,
        )

    def action_save(self) -> None:
        try:
            backup = zellij_themes.upsert_user_theme(self.config_path, self.theme)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Error al guardar: {exc}", severity="error", timeout=10)
            return
        self.dirty = False
        self._refresh_header()
        msg = f"Tema '{self.theme.name}' guardado en config.kdl"
        if backup is not None:
            msg += f"  (backup: {backup.name})"
        self.app.notify(msg, severity="information", timeout=6)

        # Si el tema editado es el activo en Zellij, propagar a alacritty.toml.
        active = zellij_config.read_active_theme(self.config_path)
        if active == self.theme.name:
            alacritty_path = getattr(
                getattr(self.app, "paths", None), "alacritty_config", None
            )
            if alacritty_path is not None:
                try:
                    theme_sync.sync_alacritty_with_zellij_theme(
                        zellij_theme_name=self.theme.name,
                        alacritty_path=alacritty_path,
                        zellij_config_path=self.config_path,
                    )
                except Exception as exc:  # noqa: BLE001
                    self.app.notify(
                        f"Error sincronizando Alacritty: {exc}",
                        severity="error",
                        timeout=8,
                    )

        register = getattr(self.app, "register_zellij_themes", None)
        if callable(register):
            register()
        if getattr(self.app, "theme", None) == self.theme.name:
            applier = getattr(self.app, "apply_theme_for_zellij", None)
            if callable(applier):
                applier(self.theme.name)

    def action_back(self) -> None:
        if not self.dirty:
            self.app.pop_screen()
            return

        def after(ok: bool) -> None:
            if ok:
                self.app.pop_screen()

        self.app.push_screen(
            ConfirmByNameModal(
                title="Hay cambios sin guardar",
                message=(
                    "Si vuelves ahora, perderas los cambios del tema. "
                    "Cancela y pulsa s para guardar."
                ),
                expected="descartar",
                confirm_label="Descartar cambios",
            ),
            after,
        )
