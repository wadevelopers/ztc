from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from ztc.services import theme_sync
from ztc.widgets.confirm import ConfirmByNameModal, PromptModal
from ztc.widgets.header import StaticHeader
from ztc.zellij import config_ops, theme_writer
from ztc.zellij import theme_assets as zellij_theme_assets
from ztc.zellij.config import read_active_theme
from ztc.zellij.models import ZellijTheme
from ztc.zellij.user_themes import (
    is_valid_theme_name,
    list_all_themes,
    list_user_themes,
)

_HEADER_PREFIX = "header:"


class ThemePickerScreen(Screen[None]):
    """Pantalla para elegir el tema activo de Zellij."""

    BINDINGS = [
        Binding("enter", "apply", "Apply", show=True),
        Binding("n", "new_theme", "New"),
        Binding("e", "edit_theme", "Edit"),
        Binding("c", "clone_theme", "Clone"),
        Binding("d", "delete_theme", "Delete"),
        Binding("escape", "app.pop_screen", "Back", show=True),
        # `q` y `ctrl+q` neutralizados: solo `Esc` sale del editor.
        Binding("q", "noop", show=False),
        Binding("ctrl+q", "noop", show=False),
    ]

    def action_noop(self) -> None:
        pass

    DEFAULT_CSS = """
    ThemePickerScreen {
        layout: vertical;
    }
    #status {
        padding: 0 1;
        height: 1;
        color: $text-muted;
    }
    #body {
        height: 1fr;
    }
    OptionList {
        width: 40;
        border-right: solid $panel;
    }
    #info {
        padding: 1 2;
        height: 1fr;
    }
    #info-name {
        text-style: bold;
        color: $accent;
    }
    .swatch-row {
        height: 1;
    }
    """

    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config_path = config_path
        self._themes: list[ZellijTheme] = []
        self._active: str | None = None

    def compose(self) -> ComposeResult:
        yield StaticHeader()
        yield Static("", id="status")
        with Horizontal(id="body"):
            yield OptionList(id="theme-list")
            with Vertical(id="info"):
                yield Static("Select a theme to see details.", id="info-name")
                yield Static("", id="info-meta")
                yield Static("", id="info-colors")
        yield Footer()

    def on_mount(self) -> None:
        self._reload()

    def _reload(self) -> None:
        self._themes = list_all_themes(self.config_path)
        self._active = read_active_theme(self.config_path)
        self._refresh_status()

        option_list = self.query_one("#theme-list", OptionList)
        option_list.clear_options()

        user_themes = [t for t in self._themes if t.is_user]
        builtin_themes = [t for t in self._themes if not t.is_user]

        active_index: int | None = None

        def add_section(header_id: str, header_label: str, themes: list[ZellijTheme]) -> None:
            nonlocal active_index
            if not themes:
                return
            option_list.add_option(
                Option(header_label, id=_HEADER_PREFIX + header_id, disabled=True)
            )
            for theme in themes:
                option_list.add_option(Option(self._format_option(theme), id=theme.name))
                if active_index is None and theme.name == self._active:
                    active_index = option_list.option_count - 1

        add_section("user", "── User themes ──", user_themes)
        add_section("builtin", "── Built-in ──", builtin_themes)

        if option_list.option_count == 0:
            return

        # Si no hay tema activo o no esta en la lista, posicionarse en el
        # primer item seleccionable (saltando el header inicial).
        if active_index is None:
            active_index = 1 if option_list.option_count > 1 else 0
        option_list.highlighted = active_index
        opt = option_list.get_option_at_index(active_index)
        theme = self._theme_by_name(opt.id) if opt.id else None
        if theme is not None:
            self._show_info(theme)

    def _format_option(self, theme: ZellijTheme) -> str:
        marker = "* " if theme.name == self._active else "  "
        return f"{marker}{theme.name}"

    def _refresh_status(self) -> None:
        status = self.query_one("#status", Static)
        active = self._active or "(none)"
        status.update(
            f"Active theme: [b]{active}[/b]    config: {self.config_path}"
        )

    def _show_info(self, theme: ZellijTheme) -> None:
        name_widget = self.query_one("#info-name", Static)
        meta_widget = self.query_one("#info-meta", Static)
        colors_widget = self.query_one("#info-colors", Static)

        name_widget.update(theme.name)
        kind = "user-defined" if theme.is_user else "built-in"
        active_marker = "  (active)" if theme.name == self._active else ""
        meta_widget.update(f"Type: {kind}{active_marker}")

        legacy_pairs = self._legacy_pairs_for_preview(theme)
        rich_pairs = self._rich_pairs_for_preview(theme)
        if not legacy_pairs and not rich_pairs:
            colors_widget.update("No color preview. Press Enter to apply.")
            return

        lines: list[str] = []
        if legacy_pairs:
            lines.append("[dim]── ANSI palette ──[/dim]")
            for slot_name, value in legacy_pairs:
                lines.append(self._render_slot_row(slot_name, value))
        if rich_pairs:
            if lines:
                lines.append("")
            lines.append("[dim]── UI (Zellij) ──[/dim]")
            for slot_name, value in rich_pairs:
                lines.append(self._render_slot_row(slot_name, value))
        colors_widget.update("\n".join(lines))

    @staticmethod
    def _render_slot_row(name: str, value: str) -> str:
        swatch = f"[on {value}]      [/]" if _looks_like_hex(value) else "      "
        return f"{name:<28} {value:<10} {swatch}"

    def _legacy_pairs_for_preview(self, theme: ZellijTheme) -> list[tuple[str, str]]:
        if theme.colors:
            return [(c.name, c.value) for c in theme.colors]
        if theme.is_user:
            return []
        derived = zellij_theme_assets.derive_legacy_slots_from_bundled(theme.name)
        if derived is None:
            return []
        return list(derived.items())

    def _rich_pairs_for_preview(self, theme: ZellijTheme) -> list[tuple[str, str]]:
        """Slots ricos expuestos. Para user themes lee de raw_components,
        para built-in carga del .kdl vendorizado."""
        out: list[tuple[str, str]] = []
        if theme.is_user:
            for component, slot in theme_writer.RICH_SLOTS_TO_EXPOSE:
                value = theme_writer.get_rich_slot(theme, component, slot)
                if value is not None:
                    out.append((theme_writer.display_slot(component, slot), value))
            return out

        bundled = zellij_theme_assets.load_bundled_theme(theme.name)
        if bundled is None:
            return out
        for component, slot in theme_writer.RICH_SLOTS_TO_EXPOSE:
            comp = bundled.components.get(component)
            if comp is None:
                continue
            value = getattr(comp, slot, None)
            if value is not None:
                out.append((theme_writer.display_slot(component, slot), value))
        return out

    @on(OptionList.OptionHighlighted, "#theme-list")
    def _on_highlight(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is None or event.option.id.startswith(_HEADER_PREFIX):
            return
        theme = self._theme_by_name(event.option.id)
        if theme is not None:
            self._show_info(theme)

    @on(OptionList.OptionSelected, "#theme-list")
    def _on_select(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None or event.option.id.startswith(_HEADER_PREFIX):
            return
        self._apply(event.option.id)

    def action_apply(self) -> None:
        option_list = self.query_one("#theme-list", OptionList)
        if option_list.highlighted is None:
            return
        option = option_list.get_option_at_index(option_list.highlighted)
        if option.id is None or option.id.startswith(_HEADER_PREFIX):
            return
        self._apply(option.id)

    def _apply(self, name: str) -> None:
        if name == self._active:
            self.app.notify(f"'{name}' is already the active theme", severity="information")
            return
        try:
            backup = config_ops.set_active_theme(self.config_path, name)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Error applying theme: {exc}", severity="error", timeout=8)
            return
        msg = f"Zellij theme '{name}' applied"
        if backup is not None:
            msg += f" (backup: {backup.name})"
        self.app.notify(msg, severity="information", timeout=6)
        # Sincronizar Alacritty con el tema Zellij recien aplicado.
        self._sync_alacritty(name)
        # Sincronizar el tema del TUI.
        self._sync_app_theme(name)
        self._reload()

    def _sync_alacritty(self, zellij_name: str) -> None:
        """Propaga bg/fg/normal.* al backend de la terminal. No bloqueante: si falla, avisa."""
        backend = getattr(self.app, "backend", None)
        backend_path = getattr(self.app, "backend_path", None)
        if backend is None or backend_path is None:
            return
        try:
            result = theme_sync.sync_terminal_with_zellij_theme(
                zellij_theme_name=zellij_name,
                backend=backend,
                backend_path=backend_path,
                zellij_config_path=self.config_path,
            )
        except Exception as exc:  # noqa: BLE001
            self.app.notify(
                f"Error syncing terminal: {exc}",
                severity="error",
                timeout=8,
            )
            return
        if result.skipped_reason:
            self.app.notify(
                f"{backend.display_name} not updated: {result.skipped_reason}",
                severity="warning",
                timeout=6,
            )
            return
        n = len(result.updated)
        msg = f"{backend.display_name} updated: {n} slot(s)"
        if result.backup is not None:
            msg += f" (backup: {result.backup.name})"
        self.app.notify(msg, severity="information", timeout=6)

    def _sync_app_theme(self, name: str) -> None:
        """Re-registra (por si era un user theme nuevo/editado) y aplica."""
        register = getattr(self.app, "register_zellij_themes", None)
        if callable(register):
            register()
        applier = getattr(self.app, "apply_theme_for_zellij", None)
        if callable(applier):
            applier(name)

    def _theme_by_name(self, name: str) -> ZellijTheme | None:
        return next((t for t in self._themes if t.name == name), None)

    def _highlighted(self) -> ZellijTheme | None:
        option_list = self.query_one("#theme-list", OptionList)
        if option_list.highlighted is None:
            return None
        opt = option_list.get_option_at_index(option_list.highlighted)
        if opt.id is None or opt.id.startswith(_HEADER_PREFIX):
            return None
        return self._theme_by_name(opt.id)

    def on_screen_resume(self) -> None:
        # Tras volver del editor de custom themes, refrescar para ver cambios.
        self._reload()

    # ---------- acciones de custom themes ----------

    def action_new_theme(self) -> None:
        def after(name: str | None) -> None:
            if not name:
                return
            if not is_valid_theme_name(name):
                self.app.notify(
                    f"Invalid name: {name!r}. "
                    "Start with a letter; use letters, numbers, '_' or '-'.",
                    severity="error",
                    timeout=8,
                )
                return
            current_names = {t.name for t in list_user_themes(self.config_path)}
            if name in current_names:
                self.app.notify(
                    f"User theme '{name}' already exists. Use a different name.",
                    severity="error",
                )
                return
            from ztc.screens.custom_theme_editor import CustomThemeEditorScreen
            from ztc.zellij.models import ZellijTheme as _ZT

            new_theme = _ZT(
                name=name,
                source="user",
                colors=theme_writer.default_legacy_slots(),
            )
            self.app.push_screen(
                CustomThemeEditorScreen(
                    config_path=self.config_path, theme=new_theme
                )
            )

        self.app.push_screen(
            PromptModal(
                title="New user theme",
                placeholder="e.g. my-theme",
                confirm_label="Create",
            ),
            after,
        )

    def action_edit_theme(self) -> None:
        theme = self._highlighted()
        if theme is None:
            return
        if not theme.is_user:
            self.app.notify(
                f"'{theme.name}' is a built-in. Use Clone (c) to create an editable copy.",
                severity="warning",
                timeout=8,
            )
            return
        from ztc.screens.custom_theme_editor import CustomThemeEditorScreen

        self.app.push_screen(
            CustomThemeEditorScreen(config_path=self.config_path, theme=theme)
        )

    def action_clone_theme(self) -> None:
        theme = self._highlighted()
        if theme is None:
            return
        src = theme.name

        def after(dst: str | None) -> None:
            if not dst:
                return
            if not is_valid_theme_name(dst):
                self.app.notify(
                    f"Invalid name: {dst!r}.",
                    severity="error",
                )
                return
            backend = getattr(self.app, "backend", None)
            backend_path = getattr(self.app, "backend_path", None)
            try:
                backup = theme_writer.clone_theme(
                    self.config_path,
                    src,
                    dst,
                    backend=backend,
                    backend_path=backend_path,
                )
            except ValueError as exc:
                self.app.notify(str(exc), severity="error")
                return
            msg = f"Cloned '{src}' as '{dst}'"
            if backup is not None:
                msg += f"  (backup: {backup.name})"
            self.app.notify(msg, severity="information", timeout=6)
            register = getattr(self.app, "register_zellij_themes", None)
            if callable(register):
                register()
            self._reload()

        kind = "user" if theme.is_user else "built-in (default colors)"
        self.app.push_screen(
            PromptModal(
                title=f"Clone '{src}' \\[{kind}]",
                placeholder=f"{src}-copy",
                confirm_label="Clone",
            ),
            after,
        )

    def action_delete_theme(self) -> None:
        theme = self._highlighted()
        if theme is None:
            return
        if not theme.is_user:
            self.app.notify(
                f"'{theme.name}' is a built-in; cannot be deleted.",
                severity="warning",
            )
            return

        def after(ok: bool) -> None:
            if not ok:
                return
            try:
                backup = theme_writer.delete_user_theme(self.config_path, theme.name)
            except Exception as exc:  # noqa: BLE001
                self.app.notify(f"Delete error: {exc}", severity="error")
                return
            msg = f"Theme '{theme.name}' deleted"
            if backup is not None:
                msg += f"  (backup: {backup.name})"
            self.app.notify(msg, severity="information", timeout=6)
            self._reload()

        self.app.push_screen(
            ConfirmByNameModal(
                title="Delete user theme",
                message=(
                    f"This will remove '{theme.name}' from the themes block in config.kdl. "
                    "If it's the active theme, Zellij will fall back to 'default' on reload."
                ),
                expected=theme.name,
                confirm_label="Delete",
            ),
            after,
        )


def _looks_like_hex(value: str) -> bool:
    if not value.startswith("#"):
        return False
    rest = value[1:]
    return len(rest) in (3, 6, 8) and all(c in "0123456789abcdefABCDEF" for c in rest)
