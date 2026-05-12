"""Operaciones sobre el modelo de layout (independientes de la UI)."""

from __future__ import annotations

import re
from pathlib import Path

from ztc.models.layout import Layout, Pane, SplitDirection, Tab

_VALID_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")
_PERCENT_SIZE = re.compile(r"^([1-9][0-9]?|100)%$")


def is_valid_layout_name(name: str) -> bool:
    return bool(_VALID_NAME.match(name))


def is_valid_pane_size(value: str) -> bool:
    """Valida el subset estable de `size` para panes editables.

    El editor espera el valor sin sintaxis KDL: `60%`, no `"60%"`.
    Los tamanos fijos (`1`, `2`, etc.) se reservan para plugins/barras
    y no se exponen en el editor de panes normales.
    """
    value = value.strip()
    if not value:
        return True
    return bool(_PERCENT_SIZE.match(value))


def new_blank_layout(layouts_dir: Path, name: str) -> Layout:
    """Crea un layout vacio con una tab y un pane."""
    if not is_valid_layout_name(name):
        raise ValueError(f"Invalid name: {name!r}")
    return Layout(
        name=name,
        path=layouts_dir / f"{name}.kdl",
        tabs=[Tab(name="main", children=[Pane()])],
    )


def find_pane_parent(layout: Layout, tab_index: int, target: Pane) -> tuple[list[Pane], int] | None:
    """Devuelve (lista de hermanos, indice del target) o None si no se encuentra."""
    if not 0 <= tab_index < len(layout.tabs):
        return None
    tab = layout.tabs[tab_index]
    return _find_in_list(tab.children, target)


def _find_in_list(siblings: list[Pane], target: Pane) -> tuple[list[Pane], int] | None:
    for i, child in enumerate(siblings):
        if child is target:
            return siblings, i
        if child.is_container:
            result = _find_in_list(child.children, target)
            if result is not None:
                return result
    return None


def add_sibling(
    layout: Layout, tab_index: int, target: Pane, *, after: bool = True
) -> Pane | None:
    """Anade un Pane vacio como hermano del target. Devuelve el nuevo Pane."""
    found = find_pane_parent(layout, tab_index, target)
    if found is None:
        return None
    siblings, idx = found
    new_pane = Pane()
    siblings.insert(idx + 1 if after else idx, new_pane)
    return new_pane


def split_pane(
    layout: Layout,
    tab_index: int,
    target: Pane,
    *,
    direction: SplitDirection = "vertical",
) -> Pane | None:
    """Convierte un pane en contenedor con `target` y un nuevo Pane vacio.

    Si target ya es contenedor, simplemente anade un hijo nuevo en su interior.
    Devuelve el nuevo Pane creado.
    """
    if target.is_container:
        new_pane = Pane()
        target.children.append(new_pane)
        return new_pane

    found = find_pane_parent(layout, tab_index, target)
    if found is None:
        return None
    siblings, idx = found

    inner_existing = Pane(
        command=target.command,
        args=list(target.args),
        cwd=target.cwd,
        start_suspended=target.start_suspended,
        size=None,
        focus=target.focus,
        name=target.name,
        borderless=target.borderless,
        default_bg=target.default_bg,
        default_fg=target.default_fg,
        raw_unknown_nodes=list(target.raw_unknown_nodes),
    )
    inner_new = Pane()

    container = Pane(
        size=target.size,
        split_direction=direction,
        children=[inner_existing, inner_new],
    )
    siblings[idx] = container
    return inner_new


def delete_pane(layout: Layout, tab_index: int, target: Pane) -> bool:
    """Borra el pane del arbol. Devuelve True si se borro."""
    found = find_pane_parent(layout, tab_index, target)
    if found is None:
        return False
    siblings, idx = found
    del siblings[idx]
    return True


def move_pane(layout: Layout, tab_index: int, target: Pane, *, delta: int) -> bool:
    """Reordena entre hermanos. delta -1 sube, +1 baja. Devuelve True si se movio."""
    found = find_pane_parent(layout, tab_index, target)
    if found is None:
        return False
    siblings, idx = found
    new_idx = idx + delta
    if not 0 <= new_idx < len(siblings):
        return False
    siblings[idx], siblings[new_idx] = siblings[new_idx], siblings[idx]
    return True


def replace_pane(
    layout: Layout, tab_index: int, target: Pane, replacement: Pane
) -> bool:
    """Sustituye target por replacement preservando la posicion en el arbol."""
    found = find_pane_parent(layout, tab_index, target)
    if found is None:
        return False
    siblings, idx = found
    siblings[idx] = replacement
    return True


def enforce_single_pane_focus(layout: Layout, tab_index: int, focused: Pane) -> bool:
    """Deja `focused` como unico pane con focus=True dentro del tab.

    Devuelve False si `focused` no pertenece al tab indicado.
    """
    if not 0 <= tab_index < len(layout.tabs):
        return False
    panes = list(_walk_panes(layout.tabs[tab_index].children))
    if focused not in panes:
        return False
    for pane in panes:
        if pane is not focused:
            pane.focus = False
    focused.focus = True
    return True


def _walk_panes(panes: list[Pane]):
    for pane in panes:
        yield pane
        yield from _walk_panes(pane.children)


def add_tab(layout: Layout, name: str) -> Tab:
    tab = Tab(name=name, children=[Pane()])
    layout.tabs.append(tab)
    return tab


def delete_tab(layout: Layout, index: int) -> bool:
    if not 0 <= index < len(layout.tabs):
        return False
    del layout.tabs[index]
    return True


def rename_tab(layout: Layout, index: int, new_name: str) -> bool:
    if not 0 <= index < len(layout.tabs):
        return False
    layout.tabs[index].name = new_name or None
    return True


def move_tab(layout: Layout, index: int, *, delta: int) -> int | None:
    """Reordena tabs en el layout. delta -1 sube, +1 baja. Devuelve el
    nuevo indice del tab movido, o None si no se pudo mover (out of bounds)."""
    if not 0 <= index < len(layout.tabs):
        return None
    new_idx = index + delta
    if not 0 <= new_idx < len(layout.tabs):
        return None
    layout.tabs[index], layout.tabs[new_idx] = layout.tabs[new_idx], layout.tabs[index]
    return new_idx
