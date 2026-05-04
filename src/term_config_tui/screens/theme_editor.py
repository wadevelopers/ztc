from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from term_config_tui.models.theme import ZellijTheme
from term_config_tui.services import (
    theme_sync,
    zellij_config,
    zellij_theme_assets,
    zellij_themes,
)
from term_config_tui.widgets.confirm import ConfirmByNameModal, PromptModal


class ThemePickerScreen(Screen[None]):
    """Pantalla para elegir el tema activo de Zellij."""

    BINDINGS = [
        Binding("enter", "apply", "Aplicar", show=True),
        Binding("n", "new_theme", "Nuevo"),
        Binding("e", "edit_theme", "Editar"),
        Binding("c", "clone_theme", "Clonar"),
        Binding("d", "delete_theme", "Borrar"),
        Binding("escape", "app.pop_screen", "Volver", show=True),
        Binding("q", "app.pop_screen", "Volver", show=False),
    ]

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
        yield Header()
        yield Static("", id="status")
        with Horizontal(id="body"):
            yield OptionList(id="theme-list")
            with Vertical(id="info"):
                yield Static("Selecciona un tema para ver detalles.", id="info-name")
                yield Static("", id="info-meta")
                yield Static("", id="info-colors")
        yield Footer()

    def on_mount(self) -> None:
        self._reload()

    def _reload(self) -> None:
        self._themes = zellij_themes.list_all_themes(self.config_path)
        self._active = zellij_config.read_active_theme(self.config_path)
        self._refresh_status()

        option_list = self.query_one("#theme-list", OptionList)
        option_list.clear_options()
        active_index = 0
        for i, theme in enumerate(self._themes):
            label = self._format_option(theme)
            option_list.add_option(Option(label, id=theme.name))
            if theme.name == self._active:
                active_index = i
        if self._themes:
            option_list.highlighted = active_index
            self._show_info(self._themes[active_index])

    def _format_option(self, theme: ZellijTheme) -> str:
        marker = "* " if theme.name == self._active else "  "
        tag = "[user]" if theme.is_user else "[builtin]"
        return f"{marker}{theme.name:<24} {tag}"

    def _refresh_status(self) -> None:
        status = self.query_one("#status", Static)
        active = self._active or "(ninguno)"
        status.update(
            f"Tema activo: [b]{active}[/b]    config: {self.config_path}"
        )

    def _show_info(self, theme: ZellijTheme) -> None:
        name_widget = self.query_one("#info-name", Static)
        meta_widget = self.query_one("#info-meta", Static)
        colors_widget = self.query_one("#info-colors", Static)

        name_widget.update(theme.name)
        kind = "user-defined" if theme.is_user else "built-in"
        active_marker = "  (activo)" if theme.name == self._active else ""
        meta_widget.update(f"Tipo: {kind}{active_marker}")

        slot_pairs = self._slot_pairs_for_preview(theme)
        if slot_pairs:
            lines = []
            for slot_name, value in slot_pairs:
                swatch = (
                    f"[on {value}]      [/]" if _looks_like_hex(value) else "      "
                )
                lines.append(f"{slot_name:<20} {value:<10} {swatch}")
            colors_widget.update("\n".join(lines))
        else:
            colors_widget.update("Sin preview de colores. Pulsa Enter para aplicar.")

    def _slot_pairs_for_preview(self, theme: ZellijTheme) -> list[tuple[str, str]]:
        """Slots para preview. User themes: tal cual. Built-in: derivados
        del .kdl vendorizado (con overrides aplicados). Si el built-in no
        esta vendorizado, lista vacia."""
        if theme.colors:
            return [(c.name, c.value) for c in theme.colors]
        if theme.is_user:
            return []
        derived = zellij_theme_assets.derive_legacy_slots_from_bundled(theme.name)
        if derived is None:
            return []
        return list(derived.items())

    @on(OptionList.OptionHighlighted, "#theme-list")
    def _on_highlight(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is None:
            return
        theme = self._theme_by_name(event.option.id)
        if theme is not None:
            self._show_info(theme)

    @on(OptionList.OptionSelected, "#theme-list")
    def _on_select(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return
        self._apply(event.option.id)

    def action_apply(self) -> None:
        option_list = self.query_one("#theme-list", OptionList)
        if option_list.highlighted is None:
            return
        option = option_list.get_option_at_index(option_list.highlighted)
        if option.id is not None:
            self._apply(option.id)

    def _apply(self, name: str) -> None:
        if name == self._active:
            self.app.notify(f"'{name}' ya es el tema activo", severity="information")
            return
        try:
            backup = zellij_config.set_active_theme(self.config_path, name)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Error al aplicar tema: {exc}", severity="error", timeout=8)
            return
        msg = f"Tema Zellij '{name}' aplicado"
        if backup is not None:
            msg += f" (backup: {backup.name})"
        self.app.notify(msg, severity="information", timeout=6)
        # Sincronizar Alacritty con el tema Zellij recien aplicado.
        self._sync_alacritty(name)
        # Sincronizar el tema del TUI.
        self._sync_app_theme(name)
        self._reload()

    def _sync_alacritty(self, zellij_name: str) -> None:
        """Propaga bg/fg/normal.* a alacritty.toml. No bloqueante: si falla, avisa."""
        alacritty_path = getattr(getattr(self.app, "paths", None), "alacritty_config", None)
        if alacritty_path is None:
            return
        try:
            result = theme_sync.sync_alacritty_with_zellij_theme(
                zellij_theme_name=zellij_name,
                alacritty_path=alacritty_path,
                zellij_config_path=self.config_path,
            )
        except Exception as exc:  # noqa: BLE001
            self.app.notify(
                f"Error al sincronizar Alacritty: {exc}",
                severity="error",
                timeout=8,
            )
            return
        if result.skipped_reason:
            self.app.notify(
                f"Alacritty no actualizado: {result.skipped_reason}",
                severity="warning",
                timeout=6,
            )
            return
        n = len(result.updated)
        msg = f"Alacritty actualizado: {n} slot(s)"
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
        if opt.id is None:
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
            if not zellij_themes.is_valid_theme_name(name):
                self.app.notify(
                    f"Nombre invalido: {name!r}. "
                    "Empieza por letra; usa letras, numeros, '_' o '-'.",
                    severity="error",
                    timeout=8,
                )
                return
            current_names = {t.name for t in zellij_themes.list_user_themes(self.config_path)}
            if name in current_names:
                self.app.notify(
                    f"Ya existe un user theme '{name}'. Usa otro nombre.",
                    severity="error",
                )
                return
            from term_config_tui.models.theme import ZellijTheme as _ZT
            from term_config_tui.screens.custom_theme_editor import CustomThemeEditorScreen

            new_theme = _ZT(
                name=name,
                source="user",
                colors=zellij_themes.default_legacy_slots(),
            )
            self.app.push_screen(
                CustomThemeEditorScreen(
                    config_path=self.config_path, theme=new_theme
                )
            )

        self.app.push_screen(
            PromptModal(
                title="Nuevo user theme",
                placeholder="ej. mi-tema",
                confirm_label="Crear",
            ),
            after,
        )

    def action_edit_theme(self) -> None:
        theme = self._highlighted()
        if theme is None:
            return
        if not theme.is_user:
            self.app.notify(
                f"'{theme.name}' es un built-in. Usa Clonar (c) para crear una copia editable.",
                severity="warning",
                timeout=8,
            )
            return
        from term_config_tui.screens.custom_theme_editor import CustomThemeEditorScreen

        self.app.push_screen(
            CustomThemeEditorScreen(config_path=self.config_path, theme=theme)
        )

    def action_clone_theme(self) -> None:
        theme = self._highlighted()
        if theme is None:
            return
        src = theme.name
        if src in zellij_theme_assets.NON_CLONEABLE_THEMES:
            self.app.notify(
                f"'{src}' no se puede clonar: usa decisiones del formato "
                "nuevo de Zellij que no se reproducen en la paleta legacy "
                "editable.",
                severity="warning",
                timeout=10,
            )
            return

        def after(dst: str | None) -> None:
            if not dst:
                return
            if not zellij_themes.is_valid_theme_name(dst):
                self.app.notify(
                    f"Nombre invalido: {dst!r}.",
                    severity="error",
                )
                return
            alacritty_path = getattr(
                getattr(self.app, "paths", None), "alacritty_config", None
            )
            try:
                backup = zellij_themes.clone_theme(
                    self.config_path,
                    src,
                    dst,
                    alacritty_path=alacritty_path,
                )
            except ValueError as exc:
                self.app.notify(str(exc), severity="error")
                return
            msg = f"Clonado '{src}' como '{dst}'"
            if backup is not None:
                msg += f"  (backup: {backup.name})"
            self.app.notify(msg, severity="information", timeout=6)
            register = getattr(self.app, "register_zellij_themes", None)
            if callable(register):
                register()
            self._reload()

        kind = "user" if theme.is_user else "built-in (colores por defecto)"
        self.app.push_screen(
            PromptModal(
                title=f"Clonar '{src}' [{kind}]",
                placeholder=f"{src}-copy",
                confirm_label="Clonar",
            ),
            after,
        )

    def action_delete_theme(self) -> None:
        theme = self._highlighted()
        if theme is None:
            return
        if not theme.is_user:
            self.app.notify(
                f"'{theme.name}' es un built-in; no se puede borrar.",
                severity="warning",
            )
            return

        def after(ok: bool) -> None:
            if not ok:
                return
            try:
                backup = zellij_themes.delete_user_theme(self.config_path, theme.name)
            except Exception as exc:  # noqa: BLE001
                self.app.notify(f"Error al borrar: {exc}", severity="error")
                return
            msg = f"Tema '{theme.name}' eliminado"
            if backup is not None:
                msg += f"  (backup: {backup.name})"
            self.app.notify(msg, severity="information", timeout=6)
            self._reload()

        self.app.push_screen(
            ConfirmByNameModal(
                title="Borrar user theme",
                message=(
                    f"Esto eliminara '{theme.name}' del bloque themes en config.kdl. "
                    "Si es el tema activo, Zellij caera al tema 'default' al recargar."
                ),
                expected=theme.name,
                confirm_label="Borrar",
            ),
            after,
        )


def _looks_like_hex(value: str) -> bool:
    if not value.startswith("#"):
        return False
    rest = value[1:]
    return len(rest) in (3, 6, 8) and all(c in "0123456789abcdefABCDEF" for c in rest)
