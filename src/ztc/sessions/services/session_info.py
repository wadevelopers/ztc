"""Lectura de los snapshots de sesión que Zellij persiste en
`~/.cache/zellij/contract_version_1/session_info/<name>/`.

Zellij escribe distinto archivo segun el estado de la sesion:

- Sesiones **vivas** (running/attached/detached): `session-metadata.kdl`
  con el snapshot estructural del estado. Schema: top-level `name "..."`,
  bloque `tabs { tab { name "..." } }` y bloque separado `panes { pane
  { id ... } }`. Los datos vienen como child-nodes con args.
  *Notable:* metadata NO incluye `command` ni `cwd` por panel — solo el
  shape estructural de los tabs/panes.

- Sesiones (vivas o **exited**): `session-layout.kdl`, el layout que
  Zellij usa para resurrect. Schema distinto: top-level `layout { tab
  name="..." { pane command="..." cwd="..." } }`. Los datos vienen como
  KDL props y los panes estan anidados dentro de cada tab. Esta es la
  unica fuente de `command` y `cwd` por panel.

`read_session_details(name)` mergea ambas fuentes cuando estan
disponibles: tabs/mtime salen de metadata (refleja el estado actual);
panes con command/cwd salen de layout (matcheando tabs por nombre).
Para exited solo hay layout, se usa entero. Si no hay nada, devuelve
None.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import kdl


@dataclass
class PaneInfo:
    command: str | None = None
    cwd: str | None = None
    size: str | None = None
    """Tamano del pane segun el layout. Puede ser absoluto ("1", "2"
    en celdas) o porcentual ("16%", "51%"). None si el layout no lo
    declara explicitamente."""
    default_bg: str | None = None
    """Color de fondo (`default_bg="#1a2030"`) si el layout lo
    declara. Util como pista visual de qué pane se está mirando."""
    split_direction: str | None = None
    """`"horizontal"` (children apilados en filas) o `"vertical"`
    (children side-by-side en columnas), si el pane es un container
    que lo declara. None para leaves o containers que heredan el
    default."""
    children: list["PaneInfo"] = field(default_factory=list)


@dataclass
class TabInfo:
    name: str
    panes: list[PaneInfo] = field(default_factory=list)


@dataclass
class SessionDetails:
    name: str
    tabs: list[TabInfo] = field(default_factory=list)
    mtime: float | None = None
    source: str = "metadata"
    """De que archivos salieron los detalles: `"metadata"` (sesion viva,
    solo tabs sin paneles), `"layout"` (sesion exited), `"merged"`
    (sesion viva con datos de paneles tomados del layout)."""


def session_info_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "zellij" / "contract_version_1" / "session_info"


def metadata_path_for(name: str) -> Path | None:
    """Ubica el `session-metadata.kdl` de la sesión. Busca primero por nombre
    exacto y, si no existe, prueba con sufijo `~` (Zellij lo agrega para
    sesiones que terminaron pero quedaron resucitables)."""
    base = session_info_dir()
    for candidate in (base / name, base / f"{name}~"):
        meta = candidate / "session-metadata.kdl"
        if meta.exists():
            return meta
    return None


def layout_path_for(name: str) -> Path | None:
    """Ubica el `session-layout.kdl` de la sesion. Para exited es el
    unico archivo que persiste; para vivas existe en paralelo a
    metadata y aporta los datos de paneles que metadata no guarda."""
    base = session_info_dir()
    for candidate in (base / name, base / f"{name}~"):
        layout = candidate / "session-layout.kdl"
        if layout.exists():
            return layout
    return None


def read_session_details(name: str) -> SessionDetails | None:
    """Parsea el snapshot de una sesion mergeando metadata + layout
    cuando ambos existen.

    - Si solo hay layout (exited): se usa como SessionDetails directo.
    - Si solo hay metadata: se usa, pero los tabs no tienen paneles
      (metadata no los persiste con command/cwd).
    - Si ambos: tabs + mtime de metadata; panes (cmd/cwd) del layout,
      matcheando por nombre de tab. Resultado: estado actual con
      richeza de paneles.
    - Si nada: None.
    """
    meta = metadata_path_for(name)
    layout = layout_path_for(name)

    metadata_details = _parse_metadata(name, meta) if meta is not None else None
    layout_details = _parse_layout(name, layout) if layout is not None else None

    if metadata_details is None and layout_details is None:
        return None
    if metadata_details is None:
        return layout_details
    if layout_details is None:
        return metadata_details
    return _merge(metadata_details, layout_details)


def _merge(meta: SessionDetails, layout: SessionDetails) -> SessionDetails:
    """Mergea metadata (tabs + mtime) con layout (panes por tab).

    Estrategia: para cada tab en metadata, si layout tiene un tab con
    el mismo nombre, le copiamos sus paneles. Si no, queda sin paneles.
    Tabs que existen solo en layout se ignoran (metadata es la fuente
    de verdad del estado actual)."""
    layout_panes_by_name: dict[str, list[PaneInfo]] = {
        t.name: t.panes for t in layout.tabs
    }
    merged_tabs = [
        TabInfo(name=t.name, panes=layout_panes_by_name.get(t.name, []))
        for t in meta.tabs
    ]
    return SessionDetails(
        name=meta.name,
        tabs=merged_tabs,
        mtime=meta.mtime,
        source="merged",
    )


# ---------- parser de session-metadata.kdl (sesiones vivas) ----------


def _parse_metadata(name: str, path: Path) -> SessionDetails | None:
    try:
        doc = kdl.parse(path.read_text(encoding="utf-8"))
    except (OSError, Exception):
        return None

    details = SessionDetails(name=name, mtime=path.stat().st_mtime, source="metadata")

    for node in doc.nodes:
        if node.name == "tabs":
            for tab in node.nodes:
                if tab.name != "tab":
                    continue
                tab_name = _child_string(tab, "name") or ""
                if tab_name:
                    details.tabs.append(TabInfo(name=tab_name))
    return details


def _child_string(node, child_name: str) -> str | None:
    """Devuelve el primer arg string del primer hijo con ese nombre.
    Formato metadata: los datos viven como child nodes con args."""
    for child in node.nodes:
        if child.name == child_name and child.args:
            value = child.args[0]
            if isinstance(value, str):
                return value
    return None


# ---------- parser de session-layout.kdl (sesiones exited o vivas) ----------


def _parse_layout(name: str, path: Path) -> SessionDetails | None:
    try:
        doc = kdl.parse(path.read_text(encoding="utf-8"))
    except (OSError, Exception):
        return None

    details = SessionDetails(name=name, mtime=path.stat().st_mtime, source="layout")

    for top in doc.nodes:
        if top.name != "layout":
            continue
        # cwd al nivel del layout: aplica por herencia a tabs/panes que
        # no lo declaren propio. Zellij usa este valor al spawnear los
        # shells, asi que reflejarlo aca es lo correcto.
        layout_cwd = _layout_level_cwd(top)
        for child in top.nodes:
            if child.name == "tab":
                tab_name = child.props.get("name")
                if not isinstance(tab_name, str):
                    continue
                tab = TabInfo(name=tab_name)
                tab_cwd = child.props.get("cwd")
                effective_cwd = tab_cwd if isinstance(tab_cwd, str) else layout_cwd
                tab.panes = _collect_layout_panes(child, parent_cwd=effective_cwd)
                details.tabs.append(tab)
    return details


def _layout_level_cwd(layout_node) -> str | None:
    """Lee el `cwd "..."` que vive en el bloque `layout { ... }` (no
    como prop, sino como child node con arg)."""
    for child in layout_node.nodes:
        if child.name == "cwd" and child.args:
            value = child.args[0]
            if isinstance(value, str):
                return value
    return None


def _collect_layout_panes(
    container, *, parent_cwd: str | None = None
) -> list[PaneInfo]:
    """Devuelve los panes hijos directos del container, recursivo para
    splits anidados. Filtra plugin-only panes (chrome de Zellij:
    status-bar, compact-bar). Propaga `cwd` por herencia con resolucion
    de paths relativos: si el pane declara `cwd="sub/path"` (relativo),
    se resuelve contra el cwd del padre, igual que hace Zellij al
    spawnear el shell."""
    out: list[PaneInfo] = []
    for child in container.nodes:
        if child.name not in {"pane", "floating_pane"}:
            continue
        if _is_chrome_plugin_pane(child):
            continue
        cmd = child.props.get("command")
        effective_cwd = _resolve_cwd(child.props.get("cwd"), parent_cwd)
        size = _format_size(child.props.get("size"))
        bg = child.props.get("default_bg")
        split = child.props.get("split_direction")
        pane = PaneInfo(
            command=cmd if isinstance(cmd, str) else None,
            cwd=effective_cwd,
            size=size,
            default_bg=bg if isinstance(bg, str) else None,
            split_direction=split if isinstance(split, str) else None,
            children=_collect_layout_panes(child, parent_cwd=effective_cwd),
        )
        out.append(pane)
    return out


def _resolve_cwd(own: object, parent_cwd: str | None) -> str | None:
    """Combina el `cwd` propio del pane con el del padre.

    - Sin `cwd` propio: hereda el del padre tal cual.
    - `cwd` absoluto: gana, ignora al padre.
    - `cwd` relativo: se resuelve contra el padre. Si no hay padre,
      se devuelve tal cual (limitacion: no podemos resolverlo)."""
    if not isinstance(own, str):
        return parent_cwd
    own_path = Path(own)
    if own_path.is_absolute():
        return own
    if parent_cwd:
        return str(Path(parent_cwd) / own_path)
    return own


def _format_size(value) -> str | None:
    """Stringifica el size del KDL. Acepta str ("16%"), int o float
    (en celdas absolutas). Devuelve None si no esta declarado."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        # KDL parsea ints como float; lo mostramos sin decimales.
        return str(int(value))
    return None


def _is_chrome_plugin_pane(pane) -> bool:
    """Detecta panes de chrome de Zellij (status-bar, compact-bar, tab-bar).
    No aportan info al usuario y solo agregan ruido al detalle."""
    for child in pane.nodes:
        if child.name == "plugin":
            location = child.props.get("location")
            if isinstance(location, str) and location.startswith("zellij:"):
                return True
    return False
