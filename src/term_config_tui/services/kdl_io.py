from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import kdl

from term_config_tui.models.layout import Layout, Pane, SplitDirection, Tab
from term_config_tui.services.atomic import write_atomic
from term_config_tui.services.backups import make_backup

# kdl-py serializa enteros como floats ("1.0"). Para no introducir ruido al
# guardar layouts existentes, los normalizamos en la salida de raw nodes.
_INTEGER_FLOAT = re.compile(r"=(\d+)\.0\b")


def load_layout(path: Path) -> Layout:
    """Carga un layout desde KDL.

    Estrategia:
    - Se entiende el subset comun: `layout { tab { pane ... } }` con `command`,
      `args`, `cwd`, `start_suspended`, `size`, `focus`, `name`, `borderless`,
      `split_direction`, y paneles anidados.
    - Nodos no entendidos (p. ej. `default_tab_template`, `plugin`) se preservan
      en `raw_unknown_nodes` para poder re-emitirlos sin perderlos.
    """
    text = path.read_text(encoding="utf-8")
    doc = kdl.parse(text)

    layout = Layout(name=path.stem, path=path)

    layout_node = next((n for n in doc.nodes if n.name == "layout"), None)
    if layout_node is None:
        # Sin nodo `layout` se devuelve un layout vacio que conserva todo crudo.
        layout.raw_unknown_nodes = list(doc.nodes)
        return layout

    layout.cwd = _str_prop(layout_node, "cwd")

    for child in layout_node.nodes:
        if child.name == "tab":
            layout.tabs.append(_parse_tab(child))
        else:
            layout.raw_unknown_nodes.append(child)
    return layout


def dump_layout(layout: Layout) -> str:
    """Emite KDL desde el modelo, preservando `raw_unknown_nodes`.

    Los nodos no entendidos (p. ej. `default_tab_template`, `plugin`) se
    re-emiten via kdl-py y se reindentan al estilo del resto del archivo.
    Limitacion conocida: nodos comentados con `/-` se pierden porque kdl-py
    no los expone al parsear.
    """
    lines: list[str] = ["layout {"]
    if layout.cwd:
        lines.append(f'    cwd "{_escape(layout.cwd)}"')
    for raw in layout.raw_unknown_nodes:
        lines.extend(_emit_raw_kdl_node(raw, indent=1))
    for tab in layout.tabs:
        lines.extend(_emit_tab(tab, indent=1))
    lines.append("}")
    return "\n".join(lines) + "\n"


def _emit_raw_kdl_node(node: object, *, indent: int) -> list[str]:
    """Re-emite un nodo opaco (kdl.Node) e indenta para alinearlo con el resto."""
    pad = "    " * indent
    text = _INTEGER_FLOAT.sub(r"=\1", str(node)).rstrip("\n")
    out: list[str] = []
    for line in text.splitlines():
        normalized = line.replace("\t", "    ")
        out.append(pad + normalized if normalized else pad)
    return out


# ---------- helpers de parseo ----------


def _parse_tab(node: kdl.Node) -> Tab:
    tab = Tab(
        name=_str_prop(node, "name"),
        focus=_bool_prop(node, "focus", False),
        cwd=_str_prop(node, "cwd"),
        split_direction=_split_dir_prop(node, "split_direction"),
    )
    for child in node.nodes:
        if child.name == "pane":
            tab.children.append(_parse_pane(child))
        else:
            tab.raw_unknown_nodes.append(child)
    return tab


_PANE_CHILD_FIELDS = {
    "command",
    "cwd",
    "start_suspended",
    "size",
    "focus",
    "name",
    "borderless",
    "split_direction",
}


def _parse_pane(node: kdl.Node) -> Pane:
    pane = Pane(
        command=_str_prop(node, "command"),
        cwd=_str_prop(node, "cwd"),
        start_suspended=_bool_prop(node, "start_suspended", False),
        size=_size_prop(node, "size"),
        focus=_bool_prop(node, "focus", False),
        name=_str_prop(node, "name"),
        borderless=_bool_prop(node, "borderless", False),
        split_direction=_split_dir_prop(node, "split_direction"),
    )
    for child in node.nodes:
        if child.name == "pane":
            pane.children.append(_parse_pane(child))
        elif child.name == "args":
            pane.args = [str(a) for a in child.args]
        elif child.name in _PANE_CHILD_FIELDS:
            _apply_child_field(pane, child)
        else:
            pane.raw_unknown_nodes.append(child)
    return pane


def _apply_child_field(pane: Pane, child: kdl.Node) -> None:
    """Acepta la forma KDL `key value` (nodo hijo) ademas de `key=value` (prop)."""
    if not child.args:
        return
    value = child.args[0]
    name = child.name
    if name == "command" and pane.command is None:
        pane.command = str(value)
    elif name == "cwd" and pane.cwd is None:
        pane.cwd = str(value)
    elif name == "start_suspended":
        pane.start_suspended = bool(value)
    elif name == "size" and pane.size is None:
        if isinstance(value, float) and value.is_integer():
            pane.size = str(int(value))
        else:
            pane.size = str(value)
    elif name == "focus":
        pane.focus = bool(value)
    elif name == "name" and pane.name is None:
        pane.name = str(value)
    elif name == "borderless":
        pane.borderless = bool(value)
    elif (
        name == "split_direction"
        and pane.split_direction is None
        and value in ("vertical", "horizontal")
    ):
        pane.split_direction = value  # type: ignore[assignment]


def _str_prop(node: kdl.Node, key: str) -> str | None:
    val = node.props.get(key)
    if val is None:
        return None
    return str(val)


def _bool_prop(node: kdl.Node, key: str, default: bool) -> bool:
    val = node.props.get(key)
    if val is None:
        return default
    return bool(val)


def _size_prop(node: kdl.Node, key: str) -> str | None:
    val = node.props.get(key)
    if val is None:
        return None
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val)


def _split_dir_prop(node: kdl.Node, key: str) -> SplitDirection | None:
    val = _str_prop(node, key)
    if val in ("vertical", "horizontal"):
        return val  # type: ignore[return-value]
    return None


# ---------- helpers de emision ----------


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _emit_tab(tab: Tab, *, indent: int) -> list[str]:
    pad = "    " * indent
    props = _emit_props(
        ("name", tab.name, _emit_str),
        ("focus", tab.focus, _emit_bool_if_true),
        ("cwd", tab.cwd, _emit_str),
        ("split_direction", tab.split_direction, _emit_str),
    )
    header = f"{pad}tab" + (f" {props}" if props else "")
    has_block = bool(tab.children) or bool(tab.raw_unknown_nodes)
    if not has_block:
        return [header]
    lines = [f"{header} {{"]
    for raw in tab.raw_unknown_nodes:
        lines.extend(_emit_raw_kdl_node(raw, indent=indent + 1))
    for child in tab.children:
        lines.extend(_emit_pane(child, indent=indent + 1))
    lines.append(f"{pad}}}")
    return lines


def _emit_pane(pane: Pane, *, indent: int) -> list[str]:
    pad = "    " * indent
    props = _emit_props(
        ("command", pane.command, _emit_str),
        ("cwd", pane.cwd, _emit_str),
        ("start_suspended", pane.start_suspended, _emit_bool_if_true),
        ("size", pane.size, _emit_size),
        ("focus", pane.focus, _emit_bool_if_true),
        ("name", pane.name, _emit_str),
        ("borderless", pane.borderless, _emit_bool_if_true),
        ("split_direction", pane.split_direction, _emit_str),
    )
    header = f"{pad}pane" + (f" {props}" if props else "")
    has_block = bool(pane.children) or bool(pane.args) or bool(pane.raw_unknown_nodes)
    if not has_block:
        return [header]
    lines = [f"{header} {{"]
    if pane.args:
        args_quoted = " ".join(f'"{_escape(a)}"' for a in pane.args)
        lines.append(f"{pad}    args {args_quoted}")
    for raw in pane.raw_unknown_nodes:
        lines.extend(_emit_raw_kdl_node(raw, indent=indent + 1))
    for child in pane.children:
        lines.extend(_emit_pane(child, indent=indent + 1))
    lines.append(f"{pad}}}")
    return lines


def _emit_props(*specs: tuple[str, Any, Any]) -> str:
    parts: list[str] = []
    for key, value, fmt in specs:
        rendered = fmt(key, value)
        if rendered is not None:
            parts.append(rendered)
    return " ".join(parts)


def _emit_str(key: str, value: str | None) -> str | None:
    if value is None:
        return None
    return f'{key}="{_escape(value)}"'


def _emit_bool_if_true(key: str, value: bool) -> str | None:
    if not value:
        return None
    return f"{key}=true"


def _emit_size(key: str, value: str | None) -> str | None:
    if value is None:
        return None
    if value.isdigit():
        return f"{key}={value}"
    return f'{key}="{_escape(value)}"'


def write_layout(layout: Layout, *, backup: bool = True) -> Path | None:
    """Serializa el layout y lo escribe atomicamente. Crea backup si existia."""
    backup_path = make_backup(layout.path) if backup and layout.path.exists() else None
    write_atomic(layout.path, dump_layout(layout))
    return backup_path


def delete_layout(path: Path) -> Path | None:
    """Borra un archivo de layout. Antes hace backup. Devuelve la ruta del backup."""
    if not path.exists():
        return None
    backup_path = make_backup(path)
    path.unlink()
    return backup_path


__all__ = [
    "Layout",
    "Pane",
    "Tab",
    "SplitDirection",
    "load_layout",
    "dump_layout",
    "write_layout",
    "delete_layout",
]
