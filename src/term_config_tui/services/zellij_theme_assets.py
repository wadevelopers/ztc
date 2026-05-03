"""Carga de los temas built-in de Zellij vendorizados y construccion de
temas Textual con los hex exactos.

Los .kdl viven en src/term_config_tui/assets/zellij_themes/ y vienen del repo
oficial https://github.com/zellij-org/zellij (MIT). Estan en el formato nuevo
(componentes UI: text_unselected, ribbon_selected, etc., con RGB triples).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from typing import TYPE_CHECKING

import kdl

if TYPE_CHECKING:
    from textual.theme import Theme as TextualTheme

ASSETS_PACKAGE = "term_config_tui.assets.zellij_themes"

# Componentes UI relevantes para el mapping a Textual.
_RELEVANT_COMPONENTS = (
    "text_unselected",
    "text_selected",
    "ribbon_selected",
    "ribbon_unselected",
    "frame_selected",
    "frame_highlight",
    "exit_code_success",
    "exit_code_error",
    "table_title",
)


@dataclass
class ZellijUIComponent:
    base: str | None = None
    background: str | None = None
    emphasis_0: str | None = None
    emphasis_1: str | None = None
    emphasis_2: str | None = None
    emphasis_3: str | None = None


@dataclass
class ZellijUITheme:
    """Tema Zellij en formato nuevo (componentes UI)."""

    name: str
    components: dict[str, ZellijUIComponent] = field(default_factory=dict)


# ---------- carga ----------


def list_bundled_theme_names() -> list[str]:
    """Devuelve los nombres (stem sin .kdl) ordenados alfabeticamente."""
    out: list[str] = []
    try:
        for entry in resources.files(ASSETS_PACKAGE).iterdir():
            if entry.name.endswith(".kdl"):
                out.append(entry.name[:-4])
    except (FileNotFoundError, ModuleNotFoundError):
        return []
    return sorted(out)


def load_bundled_theme(name: str) -> ZellijUITheme | None:
    """Lee y parsea un theme empaquetado por nombre. None si no existe."""
    try:
        text = (resources.files(ASSETS_PACKAGE) / f"{name}.kdl").read_text(
            encoding="utf-8"
        )
    except (FileNotFoundError, ModuleNotFoundError):
        return None
    return _parse_theme_text(text, expected_name=name)


def load_all_bundled_themes() -> list[ZellijUITheme]:
    out: list[ZellijUITheme] = []
    for name in list_bundled_theme_names():
        theme = load_bundled_theme(name)
        if theme is not None:
            out.append(theme)
    return out


def _parse_theme_text(text: str, *, expected_name: str | None = None) -> ZellijUITheme | None:
    try:
        doc = kdl.parse(text)
    except Exception:
        return None
    themes_node = next((n for n in doc.nodes if n.name == "themes"), None)
    if themes_node is None or not themes_node.nodes:
        return None
    # Cada archivo trae un solo tema bajo `themes { name { ... } }`.
    theme_node = themes_node.nodes[0]
    name = theme_node.name
    if expected_name is not None and name != expected_name:
        # Algunos archivos pueden no coincidir; preferimos el del archivo.
        pass

    components: dict[str, ZellijUIComponent] = {}
    for child in theme_node.nodes:
        if child.name not in _RELEVANT_COMPONENTS:
            continue
        components[child.name] = _parse_component(child)
    return ZellijUITheme(name=name, components=components)


def _parse_component(node: kdl.Node) -> ZellijUIComponent:
    comp = ZellijUIComponent()
    for slot_node in node.nodes:
        value = _rgb_args_to_hex(slot_node.args)
        if value is None:
            continue
        if hasattr(comp, slot_node.name):
            setattr(comp, slot_node.name, value)
    return comp


def _rgb_args_to_hex(args: list) -> str | None:
    """Convierte argumentos KDL (RGB triples como 255 200 100) a '#rrggbb'.

    Tolera enteros y floats. Single-arg como `0` se interpreta como
    'sin color' y devuelve None (Zellij usa esto como transparente).
    """
    if not args:
        return None
    nums: list[int] = []
    for a in args:
        if isinstance(a, (int, float)):
            nums.append(int(a))
        else:
            return None
    if len(nums) == 1:
        return None  # transparente / default terminal
    if len(nums) < 3:
        return None
    r, g, b = nums[0], nums[1], nums[2]
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------- mapping a Textual ----------


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    if not value or not value.startswith("#"):
        return None
    s = value[1:]
    if len(s) != 6:
        return None
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return None


def _rel_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _pick_background(
    text_un: ZellijUIComponent | None,
    text_sel: ZellijUIComponent | None,
) -> str:
    """Elige el bg representativo del tema. Ver doctring de build_textual_theme."""
    candidates = [
        (text_un.background if text_un else None),
        (text_sel.background if text_sel else None),
    ]
    for value in candidates:
        if value and value != "#000000":
            return value
    # Si todo es black/transparente, devolver lo que haya o un negro razonable.
    for value in candidates:
        if value:
            return value
    return "#1e1e1e"


def _is_dark(hex_value: str | None) -> bool:
    rgb = _hex_to_rgb(hex_value or "")
    if rgb is None:
        return True
    return _rel_luminance(rgb) < 0.5


def build_textual_theme(theme: ZellijUITheme) -> TextualTheme | None:
    """Construye un Theme de Textual desde un ZellijUITheme.

    Mapping (basado en la semantica de cada componente Zellij):
    - background    <- text_selected.background  (la BG real del tema)
    - foreground    <- text_unselected.base      (color de texto principal)
    - surface       <- text_unselected.background (BG alternativa)
    - primary       <- ribbon_selected.background (color "interactivo" del tema)
    - accent        <- frame_highlight.base      (highlights)
    - secondary     <- ribbon_unselected.background
    - error         <- exit_code_error.base
    - success       <- exit_code_success.base
    - warning       <- table_title.emphasis_0
    - dark          <- luminancia(background) < 0.5

    Devuelve None si el tema no tiene los slots minimos imprescindibles
    (text_unselected.base) — ej. formato no soportado.
    """
    from textual.theme import Theme

    text_un = theme.components.get("text_unselected")
    text_sel = theme.components.get("text_selected")
    ribbon_sel = theme.components.get("ribbon_selected")
    ribbon_un = theme.components.get("ribbon_unselected")
    frame_hl = theme.components.get("frame_highlight")
    exit_err = theme.components.get("exit_code_error")
    exit_ok = theme.components.get("exit_code_success")
    table = theme.components.get("table_title")

    if text_un is None or text_un.base is None:
        return None

    # Preferimos text_unselected.background si es un color real. Para temas
    # como dracula que ponen `0 0 0` (placeholder transparente para usar el
    # bg del terminal), caemos a text_selected.background, que es el bg
    # canonico del tema.
    background = _pick_background(text_un, text_sel)
    foreground = text_un.base
    surface = (text_un and text_un.background) or background
    primary = (
        (ribbon_sel and ribbon_sel.background)
        or (frame_hl and frame_hl.base)
        or foreground
    )
    accent = (
        (frame_hl and frame_hl.base)
        or (ribbon_sel and ribbon_sel.emphasis_0)
        or primary
    )
    secondary = (ribbon_un and ribbon_un.background) or background
    error = (
        (exit_err and exit_err.base)
        or (ribbon_sel and ribbon_sel.emphasis_0)
        or "#ff5555"
    )
    success = (
        (exit_ok and exit_ok.base)
        or (ribbon_sel and ribbon_sel.background)
        or "#50fa7b"
    )
    warning = (
        (table and table.emphasis_0)
        or (frame_hl and frame_hl.base)
        or "#f1fa8c"
    )

    return Theme(
        name=theme.name,
        primary=primary,
        secondary=secondary,
        accent=accent,
        background=background,
        surface=surface,
        foreground=foreground,
        success=success,
        warning=warning,
        error=error,
        dark=_is_dark(background),
    )


def build_textual_theme_from_legacy(
    name: str, slots: dict[str, str]
) -> TextualTheme | None:
    """Construye un Theme de Textual desde slots legacy (fg, bg, red, ...).

    Usado para user themes en formato clasico (como custom_dark).
    """
    from textual.theme import Theme

    fg = slots.get("fg")
    bg = slots.get("bg")
    if fg is None or bg is None:
        return None

    return Theme(
        name=name,
        primary=slots.get("blue") or fg,
        secondary=slots.get("magenta") or fg,
        accent=slots.get("cyan") or slots.get("magenta") or fg,
        background=bg,
        surface=bg,
        foreground=fg,
        success=slots.get("green") or "#50fa7b",
        warning=slots.get("yellow") or "#f1fa8c",
        error=slots.get("red") or "#ff5555",
        dark=_is_dark(bg),
    )
