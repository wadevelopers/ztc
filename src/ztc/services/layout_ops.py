"""Operaciones sobre el modelo de layout (independientes de la UI)."""

from __future__ import annotations

import re
from pathlib import Path

from ztc.models.layout import Layout, Pane, SplitDirection, Tab

_VALID_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")


def is_valid_layout_name(name: str) -> bool:
    return bool(_VALID_NAME.match(name))


def new_blank_layout(layouts_dir: Path, name: str) -> Layout:
    """Crea un layout vacio con una tab y un pane."""
    if not is_valid_layout_name(name):
        raise ValueError(f"Nombre invalido: {name!r}")
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


def resize_pane(target: Pane, *, delta_pct: int) -> bool:
    """Ajusta size en porcentajes. Solo opera si size es 'X%' o esta vacio.

    delta_pct positivo aumenta, negativo disminuye. Limita entre 5% y 95%.
    Si size estaba vacio, parte de 50%.
    Devuelve True si cambio.
    """
    current = target.size or ""
    m = re.match(r"^(\d+)%$", current.strip())
    if m:
        pct = int(m.group(1))
    elif current == "":
        pct = 50
    else:
        return False
    new_pct = max(5, min(95, pct + delta_pct))
    if new_pct == pct and current != "":
        return False
    target.size = f"{new_pct}%"
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
