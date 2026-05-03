"""Carga de los temas built-in de Zellij vendorizados y construccion de
temas Textual con los hex exactos.

Los .kdl viven en src/term_config_tui/assets/zellij_themes/ y vienen del repo
oficial https://github.com/zellij-org/zellij (MIT). Estan en el formato nuevo
(componentes UI: text_unselected, ribbon_selected, etc., con RGB triples).

Reglas para extraer paleta legacy (fg, bg, red, ...) desde el formato nuevo:
una sola regla, sin fallbacks. Si un tema queda mal con esta regla, se
corrige puntualmente en `THEME_OVERRIDES`.

Regla:
- bg          <- text_unselected.background
- fg          <- text_unselected.base
- black       <- text_selected.background
- red         <- exit_code_error.base
- green       <- exit_code_success.base
- yellow      <- table_title.emphasis_0
- blue        <- ribbon_selected.emphasis_3
- magenta     <- frame_highlight.emphasis_0
- cyan        <- text_unselected.emphasis_1
- white       <- text_unselected.base
- orange      <- text_unselected.emphasis_0

Cuando un tema reporta un slot incorrecto, se anade en THEME_OVERRIDES con
el comentario que explica por que (ej. dracula usa #000000 como
placeholder transparente en text_unselected.background).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from typing import TYPE_CHECKING

import kdl

if TYPE_CHECKING:
    from textual.theme import Theme as TextualTheme

ASSETS_PACKAGE = "term_config_tui.assets.zellij_themes"

# Correcciones puntuales para temas vendorizados cuyo dato crudo no produce
# el slot legacy esperado. Cada entrada apunta a slots LEGACY (fg, bg,
# black, red, green, yellow, blue, magenta, cyan, white, orange).
#
# Filosofia: una sola regla de extraccion, sin condicionales por tema dentro
# del codigo. Cuando algo sale mal, se anade aqui con su motivo.
THEME_OVERRIDES: dict[str, dict[str, str]] = {
    # text_unselected.base = #fcfcfc (blanco) no contrasta con bg light.
    # El "fg oscuro" de ayu-light vive en ribbon_unselected.background.
    "ayu-light": {"fg": "#5c6166"},
}

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


def _is_dark(hex_value: str | None) -> bool:
    rgb = _hex_to_rgb(hex_value or "")
    if rgb is None:
        return True
    return _rel_luminance(rgb) < 0.5


def load_bundled_raw_components(name: str) -> list:
    """Devuelve los nodos kdl-py del formato nuevo (text_unselected, etc.)
    del .kdl vendorizado. Lista vacia si no hay tema o no tiene componentes.
    Estos nodos son opacos: se preservan tal cual para re-emitir.
    """
    try:
        text = (resources.files(ASSETS_PACKAGE) / f"{name}.kdl").read_text(
            encoding="utf-8"
        )
    except (FileNotFoundError, ModuleNotFoundError):
        return []
    try:
        doc = kdl.parse(text)
    except Exception:
        return []
    themes_node = next((n for n in doc.nodes if n.name == "themes"), None)
    if themes_node is None or not themes_node.nodes:
        return []
    theme_node = themes_node.nodes[0]
    return [child for child in theme_node.nodes if child.nodes]


def derive_legacy_slots_from_bundled(name: str) -> dict[str, str] | None:
    """Devuelve un dict slot_name -> hex aplicando la regla unica + overrides.

    Devuelve None si no hay tema vendorizado con ese nombre.
    """
    bundled = load_bundled_theme(name)
    if bundled is None:
        return None
    return _derive_with_overrides(name, bundled)


def _derive_with_overrides(name: str, bundled: ZellijUITheme) -> dict[str, str]:
    text_un = bundled.components.get("text_unselected") or ZellijUIComponent()
    text_sel = bundled.components.get("text_selected") or ZellijUIComponent()
    ribbon_sel = bundled.components.get("ribbon_selected") or ZellijUIComponent()
    frame_hl = bundled.components.get("frame_highlight") or ZellijUIComponent()
    exit_err = bundled.components.get("exit_code_error") or ZellijUIComponent()
    exit_ok = bundled.components.get("exit_code_success") or ZellijUIComponent()
    table = bundled.components.get("table_title") or ZellijUIComponent()

    fg = text_un.base or "#cccccc"
    bg = text_un.background or "#000000"
    derived: dict[str, str] = {
        "fg": fg,
        "bg": bg,
        "black": text_sel.background or "#000000",
        "red": exit_err.base or "#ff5555",
        "green": exit_ok.base or "#50fa7b",
        "yellow": table.emphasis_0 or "#f1fa8c",
        "blue": ribbon_sel.emphasis_3 or fg,
        "magenta": frame_hl.emphasis_0 or fg,
        "cyan": text_un.emphasis_1 or fg,
        "white": fg,
        "orange": text_un.emphasis_0 or "#ff8800",
    }
    overrides = THEME_OVERRIDES.get(name, {})
    derived.update(overrides)
    return derived


def build_textual_theme(theme: ZellijUITheme) -> TextualTheme | None:
    """Construye un Theme de Textual desde un ZellijUITheme.

    Aplica la regla unica + THEME_OVERRIDES para fg/bg. Para los demas
    tokens (primary, accent, etc.) usa los componentes ricos:
    - primary       <- ribbon_selected.background  (color "interactivo")
    - accent        <- frame_highlight.base
    - secondary     <- ribbon_unselected.background
    - error         <- exit_code_error.base
    - success       <- exit_code_success.base
    - warning       <- table_title.emphasis_0
    - dark          <- luminancia(background) < 0.5

    Devuelve None si el tema no tiene text_unselected (formato no soportado).
    """
    from textual.theme import Theme

    text_un = theme.components.get("text_unselected")
    if text_un is None or text_un.base is None:
        return None

    slots = _derive_with_overrides(theme.name, theme)
    background = slots["bg"]
    foreground = slots["fg"]

    ribbon_sel = theme.components.get("ribbon_selected")
    ribbon_un = theme.components.get("ribbon_unselected")
    frame_hl = theme.components.get("frame_highlight")
    exit_err = theme.components.get("exit_code_error")
    exit_ok = theme.components.get("exit_code_success")
    table = theme.components.get("table_title")

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
    error = (exit_err and exit_err.base) or "#ff5555"
    success = (exit_ok and exit_ok.base) or "#50fa7b"
    warning = (table and table.emphasis_0) or "#f1fa8c"

    return Theme(
        name=theme.name,
        primary=primary,
        secondary=secondary,
        accent=accent,
        background=background,
        surface=background,
        foreground=foreground,
        success=success,
        warning=warning,
        error=error,
        dark=_is_dark(background),
    )


def build_textual_theme_from_legacy(
    name: str,
    slots: dict[str, str],
    *,
    raw_components: list | None = None,
) -> TextualTheme | None:
    """Construye un Theme de Textual desde slots legacy (fg, bg, red, ...).

    Si `raw_components` contiene nodos del formato nuevo (text_unselected,
    ribbon_selected, etc.), se usan PARA primary/accent/error/etc., con
    los slots legacy del usuario (fg/bg) overlayando background y
    foreground. Esto da fidelidad maxima al clonar built-ins, mientras
    permite que el usuario tweakee fg/bg en el editor.

    Sin raw_components, fallback al mapping legacy (blue->primary,
    cyan->accent, red->error, etc.).
    """
    from textual.theme import Theme

    fg = slots.get("fg")
    bg = slots.get("bg")
    if fg is None or bg is None:
        return None

    if raw_components:
        ui = _ui_theme_from_raw(name, raw_components)
        rich = build_textual_theme(ui) if ui else None
        if rich is not None:
            return Theme(
                name=name,
                primary=rich.primary,
                secondary=rich.secondary,
                accent=rich.accent,
                background=bg,
                surface=bg,
                foreground=fg,
                success=rich.success,
                warning=rich.warning,
                error=rich.error,
                dark=_is_dark(bg),
            )

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


def _ui_theme_from_raw(name: str, raw_components: list) -> ZellijUITheme | None:
    """Convierte nodos kdl-py de componentes a ZellijUITheme parseado."""
    components: dict[str, ZellijUIComponent] = {}
    for rc in raw_components:
        if rc.name not in _RELEVANT_COMPONENTS:
            continue
        components[rc.name] = _parse_component(rc)
    if not components:
        return None
    return ZellijUITheme(name=name, components=components)
