from __future__ import annotations

import os
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from ztc.sessions.screens.picker import PickerScreen
from ztc.sessions.types import LaunchTarget


def _zellij_config_path() -> Path:
    """Path al config.kdl de Zellij. Respeta XDG_CONFIG_HOME."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "zellij" / "config.kdl"


class SessionLauncherApp(App[None]):
    """Launcher TUI. Cuando el usuario elige una acción que requiere salir
    a Zellij/bash, guarda el target en `self.target` y hace `exit()`. El
    `__main__` lee ese target y `os.execvp`-ea al destino."""

    TITLE = "zsm — Zellij Session Manager"

    # `ctrl+p` choca con el menu "pane" de Zellij; usamos `P` (Shift+P).
    # Binding propia para overridear el label "palette" que Textual hardcodea.
    COMMAND_PALETTE_BINDING = "P"
    BINDINGS = [Binding("P", "command_palette", "Palette", priority=True, show=False)]

    def __init__(self) -> None:
        super().__init__()
        self.target: LaunchTarget = None
        self.zellij_config_path = _zellij_config_path()

    def on_mount(self) -> None:
        self._register_zellij_themes()
        self._sync_theme_with_zellij()
        self.push_screen(PickerScreen())

    # ---------- temas Textual sincronizados con Zellij ----------

    def _register_zellij_themes(self) -> None:
        """Registra los temas Textual derivados de los .kdl bundleados de
        Zellij + los user themes definidos en config.kdl. Permite que el
        TUI matchee el theme activo del usuario."""
        from zellij_themes import theme_assets, user_themes

        # Built-in vendorizados.
        for ui_theme in theme_assets.load_all_bundled_themes():
            textual_theme = theme_assets.build_textual_theme(ui_theme)
            if textual_theme is not None:
                self.register_theme(textual_theme)

        # User themes desde config.kdl. Si tienen raw_components (formato
        # nuevo), usamos el builder rich-based. Si no, fallback al legacy
        # builder sobre los slots planos (fg/bg/8 ANSI).
        for ut in user_themes.list_user_themes(self.zellij_config_path):
            ui_theme = theme_assets.user_theme_to_ui_theme(ut)
            textual_theme = (
                theme_assets.build_textual_theme(ui_theme)
                if ui_theme is not None
                else theme_assets.build_textual_theme_from_legacy(
                    ut.name, {c.name: c.value for c in ut.colors}
                )
            )
            if textual_theme is not None:
                self.register_theme(textual_theme)

    def _sync_theme_with_zellij(self) -> None:
        """Aplica el tema Textual con el mismo nombre que el tema activo
        de Zellij. Si no esta registrado, cae a `textual-dark`."""
        from zellij_themes import TEXTUAL_FALLBACK
        from zellij_themes.config import read_active_theme

        active = read_active_theme(self.zellij_config_path)
        target = active if active else TEXTUAL_FALLBACK
        if target not in self.available_themes:
            target = TEXTUAL_FALLBACK
        self.theme = target
