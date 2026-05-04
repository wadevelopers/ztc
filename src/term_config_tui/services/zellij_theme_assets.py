"""Carga de los temas built-in de Zellij vendorizados y construccion de
temas Textual con los hex exactos.

Los .kdl viven en src/term_config_tui/assets/zellij_themes/ y vienen del repo
oficial https://github.com/zellij-org/zellij (MIT). Estan en el formato nuevo
(componentes UI: text_unselected, ribbon_selected, etc., con RGB triples).

Reglas para extraer paleta legacy desde el formato nuevo. Validadas contra
la conversion oficial inversa de Zellij (impl From<Palette> for Styling
en zellij-utils/src/data.rs):

- bg       <- text_unselected.background
- black    <- text_unselected.background  (= bg; Zellij usa palette.black como bg de plugins)
- fg       <- ribbon_unselected.background  (palette.fg en la conversion)
- white    <- text_unselected.base
- red      <- exit_code_error.base
- green    <- exit_code_success.base
- yellow   <- table_title.emphasis_0
- blue     <- ribbon_selected.emphasis_3
- magenta  <- frame_highlight.emphasis_0
- cyan     <- text_unselected.emphasis_1
- orange   <- text_unselected.emphasis_0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from typing import TYPE_CHECKING

import kdl

if TYPE_CHECKING:
    from textual.theme import Theme as TextualTheme

ASSETS_PACKAGE = "term_config_tui.assets.zellij_themes"

# Correcciones puntuales sobre la paleta legacy derivada. Cada entrada
# apunta a slots LEGACY (fg, bg, black, red, green, yellow, blue,
# magenta, cyan, white, orange). Los valores aqui pisan los derivados
# del .kdl al aplicar/clonar/sincronizar el tema.
THEME_OVERRIDES: dict[str, dict[str, str]] = {
    "ayu-light": {"white": "#5c6166"},
    "catppuccin-latte": {"red": "#ea76cb"},
}

# Temas built-in que no se pueden clonar a un user theme legacy editable
# porque su rendering usa decisiones del formato nuevo que la paleta
# legacy no captura adecuadamente. El picker bloquea clonarlos.
NON_CLONEABLE_THEMES: frozenset[str] = frozenset({
    "gruber-darker",
})

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


def load_bundled_raw_components(name: str) -> list:
    """Devuelve los kdl.Node opacos de los bloques anidados (formato nuevo)
    del tema vendorizado. Lista vacia si no existe el tema o no tiene
    bloques. Estos nodos se preservan tal cual para re-emitir en clone."""
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
    """Convierte argumentos KDL a '#rrggbb'. Soporta dos formatos:

    - Hex string (user theme): un argumento como "#rrggbb" o "#rgb".
    - RGB triple (bundled): tres enteros 0-255.

    Single-int (`0`) se interpreta como transparente y devuelve None.
    """
    if not args:
        return None
    if len(args) == 1 and isinstance(args[0], str) and args[0].startswith("#"):
        return args[0].lower()
    nums: list[int] = []
    for a in args:
        if isinstance(a, (int, float)):
            nums.append(int(a))
        else:
            return None
    if len(nums) == 1:
        return None
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


def derive_legacy_slots_from_bundled(name: str) -> dict[str, str] | None:
    """Devuelve un dict slot_name -> hex aplicando la regla unica.

    Devuelve None si no hay tema vendorizado con ese nombre.
    """
    bundled = load_bundled_theme(name)
    if bundled is None:
        return None
    return _derive_slots(bundled)


def _derive_slots(bundled: ZellijUITheme) -> dict[str, str]:
    text_un = bundled.components.get("text_unselected") or ZellijUIComponent()
    ribbon_sel = bundled.components.get("ribbon_selected") or ZellijUIComponent()
    ribbon_un = bundled.components.get("ribbon_unselected") or ZellijUIComponent()
    frame_hl = bundled.components.get("frame_highlight") or ZellijUIComponent()
    exit_err = bundled.components.get("exit_code_error") or ZellijUIComponent()
    exit_ok = bundled.components.get("exit_code_success") or ZellijUIComponent()

    bg = text_un.background or "#000000"
    # fg <- ribbon_unselected.background. Confirmado en la fuente de Zellij
    # (impl From<Palette> for Styling): ribbon_unselected.background = palette.fg.
    # Es decir, el slot canonico de Zellij para "fg" en el formato nuevo.
    fg = ribbon_un.background or text_un.base or "#cccccc"
    # white <- text_unselected.base. Es el "fg secundario" usado dentro de
    # ribbons. Distinto de fg.
    white = text_un.base or fg
    derived: dict[str, str] = {
        "fg": fg,
        # bg y black derivan ambos de text_unselected.background. bg lo usan
        # Alacritty (primary.background) y el TUI (Textual). black lo usa
        # Zellij internamente como bg de sus plugins (compact-bar, status-bar,
        # etc.). Por defecto coinciden; el usuario puede editarlos por separado.
        "bg": bg,
        "black": bg,
        "red": exit_err.base or "#ff5555",
        "green": exit_ok.base or "#50fa7b",
        "yellow": exit_err.emphasis_0 or "#f1fa8c",
        "blue": ribbon_sel.emphasis_3 or fg,
        "magenta": frame_hl.emphasis_0 or fg,
        "cyan": text_un.emphasis_1 or fg,
        "white": white,
        "orange": text_un.emphasis_0 or "#ff8800",
    }
    derived.update(THEME_OVERRIDES.get(bundled.name, {}))
    return derived


def build_textual_theme(theme: ZellijUITheme) -> TextualTheme | None:
    """Construye un Theme de Textual desde un ZellijUITheme.

    fg/bg desde los slots legacy derivados. Para los demas tokens usa
    los componentes ricos:
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

    slots = _derive_slots(theme)
    background = slots["bg"]
    foreground = slots["white"]

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
    name: str, slots: dict[str, str]
) -> TextualTheme | None:
    """Construye un Theme de Textual desde slots legacy.

    Mapping segun la conversion de Zellij (impl From<Palette> for Styling):
      green   -> primary, success
      orange  -> accent, warning
      fg      -> secondary  (bg de ribbons)
      white   -> foreground (texto canonico)
      red     -> error
    """
    from textual.theme import Theme

    bg = slots.get("bg")
    foreground = slots.get("white") or slots.get("fg")
    if foreground is None or bg is None:
        return None

    orange = slots.get("orange") or slots.get("yellow") or foreground
    return Theme(
        name=name,
        primary=slots.get("green") or foreground,
        secondary=slots.get("fg") or foreground,
        accent=orange,
        background=bg,
        surface=bg,
        foreground=foreground,
        success=slots.get("green") or "#50fa7b",
        warning=orange,
        error=slots.get("red") or "#ff5555",
        dark=_is_dark(bg),
    )
