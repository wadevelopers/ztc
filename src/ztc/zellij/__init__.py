"""Stuff de Zellij: lectura de temas built-in vendorizados, parsing de
user themes, builders Textual, lectura de tema activo, models, escritura
de bloques themes/config, layouts.

Esta API publica replica la que tenia el ex-shared `zellij_themes/`
(re-exports de modulos top-level + simbolos mas usados), asi los call
sites pasan de `from zellij_themes import X` a `from ztc.zellij import X`
con cambio mecanico.
"""
from ztc.zellij import (
    config,
    config_ops,
    layout_io,
    layout_ops,
    models,
    theme_assets,
    theme_writer,
    user_themes,
)
from ztc.zellij.models import ZellijColor, ZellijTheme
from ztc.zellij.user_themes import TEXTUAL_FALLBACK

__all__ = [
    "TEXTUAL_FALLBACK",
    "ZellijColor",
    "ZellijTheme",
    "config",
    "config_ops",
    "layout_io",
    "layout_ops",
    "models",
    "theme_assets",
    "theme_writer",
    "user_themes",
]
