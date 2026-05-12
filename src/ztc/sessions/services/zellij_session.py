"""Wrappers sobre el CLI de Zellij para listar y manipular sesiones.

zsm corre **fuera** de Zellij (es el launcher), por lo que no hay
restricciones de "no podés cortar la rama". Cualquier acción es válida.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from ztc.sessions.models.session import ZellijSession

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_NO_SESSIONS = re.compile(r"no active.*sessions", re.IGNORECASE)
_EXITED_SUFFIX = re.compile(r"\(EXITED\b", re.IGNORECASE)

# Variantes conocidas con las que un cliente identifica su sesion en
# argv. Solo se usan como fallback cuando la deteccion por socket no
# pudo asignar una sesion al proceso (ej. proc fs no accesible).
_CLIENT_SESSION_PATTERNS = (
    re.compile(r"(?:^|\s)attach\s+(?P<name>\S+)"),
    re.compile(r"(?:^|\s)(?:-s|--session)\s+(?P<name>\S+)"),
    re.compile(r"(?:^|\s)--session=(?P<name>\S+)"),
)

# Path del socket de Zellij dentro de un dir de sesion. Lo usamos para
# parsear `ss -xa` y matchear inodos con nombres de sesion.
_ZELLIJ_SOCKET_PATH_RE = re.compile(
    r"/zellij/contract_version_\d+/(?P<name>[^/\s]+)"
)
_PROC_SOCKET_RE = re.compile(r"^socket:\[(\d+)\]$")


def _zellij() -> str | None:
    return shutil.which("zellij")


def _strip_ansi(s: str) -> str:
    return _ANSI.sub("", s)


def list_sessions(*, timeout: float = 5.0) -> list[ZellijSession]:
    """Lista sesiones via `zellij list-sessions -n`. Devuelve [] si no hay
    ninguna o zellij no está instalado.

    Para sesiones con server vivo, intenta refinar el estado a
    `attached` o `detached` segun haya o no clientes conectados.
    Si la deteccion de clientes falla, las sesiones quedan como
    `running` (fallback graceful, no rompe la UX)."""
    if _zellij() is None:
        return []
    try:
        proc = subprocess.run(
            ["zellij", "list-sessions", "-n"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return []

    combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    out: list[ZellijSession] = []
    seen: set[str] = set()
    for raw in combined.splitlines():
        line = _strip_ansi(raw).strip()
        if not line or _NO_SESSIONS.search(line):
            continue
        session = _parse_line(line)
        if session is not None and session.name not in seen:
            seen.add(session.name)
            out.append(session)

    # Refinar running -> attached/detached con info de procesos.
    # Si el detector falla (None), todas las running quedan como
    # "running" sin tocar.
    clients_by_session = get_attached_session_clients()
    if clients_by_session is not None:
        for s in out:
            if s.state != "running":
                continue
            count = clients_by_session.get(s.name, 0)
            if count > 0:
                s.state = "attached"
                s.attached_clients = count
            else:
                s.state = "detached"

    return out


def get_attached_session_clients(
    *, timeout: float = 2.0
) -> dict[str, int] | None:
    """Devuelve {nombre_sesion: cantidad_clientes_conectados}.

    Estrategia (más robusto que solo argv): cada cliente Zellij abre
    un socket UNIX hacia el server de su sesion. Mapeamos esos sockets
    a nombres de sesion via `ss -xa` y buscamos en `/proc/PID/fd` de
    cada proceso `zellij` cliente cual coincide. Si no se puede (no
    hay `ss`, no hay /proc, etc.) caemos a parseo de argv como
    fallback.

    Devuelve `None` si `pgrep` no esta disponible o falla; el caller
    interpreta `None` como "no se pudo determinar" y deja las sesiones
    como `running` (estado fallback)."""
    if shutil.which("pgrep") is None:
        return None
    try:
        proc = subprocess.run(
            ["pgrep", "-af", "zellij"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None

    inode_to_session = _build_inode_session_map(timeout=timeout)

    counts: dict[str, int] = {}
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # Formato: "<pid> <cmdline...>". Skip el PID.
        parts = line.split(maxsplit=1)
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        cmdline = parts[1]
        # Solo procesos cuyo binario es zellij (no "zellijthing"). Y
        # excluimos servers (--server). Solo clientes.
        if "--server" in cmdline:
            continue
        first = cmdline.split(maxsplit=1)[0] if cmdline else ""
        bin_name = first.rsplit("/", 1)[-1]
        if bin_name != "zellij":
            continue

        # Primero por socket (mas robusto: detecta tambien `zellij`
        # ejecutado solo, sin args explicitos).
        name = _session_via_sockets(pid, inode_to_session)
        if name is None:
            # Fallback: intentar extraer del argv si tiene `attach NAME`,
            # `-s NAME`, etc.
            name = _extract_client_session_name(cmdline)
        if name:
            counts[name] = counts.get(name, 0) + 1

    return counts


def _build_inode_session_map(*, timeout: float = 2.0) -> dict[int, str]:
    """Parsea `ss -xa` y devuelve {client_inode: session_name}.

    Para cada conexion ESTAB cuyo lado server tiene path
    `/run/user/UID/zellij/contract_version_X/<sesion>`, registramos el
    peer-inode (lado cliente) -> nombre de sesion. Despues, leyendo
    `/proc/PID/fd` de un cliente zellij, si alguno de sus sockets es
    una key de este map, sabemos a que sesion esta attached."""
    if shutil.which("ss") is None:
        return {}
    try:
        proc = subprocess.run(
            ["ss", "-xa"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {}

    out: dict[int, str] = {}
    for line in (proc.stdout or "").splitlines():
        if "ESTAB" not in line or "/zellij/" not in line:
            continue
        fields = line.split()
        # ss -xa output: Netid State Recv-Q Send-Q Local-Addr Local-Inode Peer-Addr Peer-Inode
        if len(fields) < 8:
            continue
        m = _ZELLIJ_SOCKET_PATH_RE.search(fields[4])
        if not m:
            continue
        try:
            peer_inode = int(fields[-1])
        except ValueError:
            continue
        out[peer_inode] = m.group("name")
    return out


def _session_via_sockets(
    pid: int, inode_to_session: dict[int, str]
) -> str | None:
    """Revisa `/proc/PID/fd` y devuelve la sesion a la que esta attached
    el proceso (si alguno de sus sockets matchea el map). None si no
    se puede determinar."""
    if not inode_to_session:
        return None
    fd_dir = Path(f"/proc/{pid}/fd")
    if not fd_dir.exists():
        return None
    try:
        for entry in fd_dir.iterdir():
            try:
                target = os.readlink(entry)
            except OSError:
                continue
            m = _PROC_SOCKET_RE.match(target)
            if not m:
                continue
            inode = int(m.group(1))
            session = inode_to_session.get(inode)
            if session is not None:
                return session
    except OSError:
        return None
    return None


def _extract_client_session_name(cmdline: str) -> str | None:
    """Intenta extraer el nombre de sesion de un argv de cliente.
    Retorna None si ninguna variante conocida matchea (ej. `zellij`
    ejecutado solo sin args)."""
    for pat in _CLIENT_SESSION_PATTERNS:
        m = pat.search(cmdline)
        if m:
            return m.group("name")
    return None


def _parse_line(line: str) -> ZellijSession | None:
    """Saca nombre y estado de una linea de `list-sessions`."""
    m = re.match(r"^EXITED\s*-\s*(?P<name>\S+)(?:\s+(?P<rest>.*))?$", line)
    if m:
        return ZellijSession(name=m.group("name"), state="exited", raw_line=line)
    m = re.match(r"^(?P<name>\S+)(?:\s+(?P<rest>.*))?$", line)
    if m:
        rest = m.group("rest") or ""
        state = "exited" if _EXITED_SUFFIX.search(rest) else "running"
        return ZellijSession(name=m.group("name"), state=state, raw_line=line)
    return None


def kill_session(name: str, *, timeout: float = 10.0) -> tuple[bool, str]:
    return _run(["zellij", "kill-session", name], timeout=timeout)


def rename_session(
    old_name: str, new_name: str, *, timeout: float = 10.0
) -> tuple[bool, str]:
    """Renombra una sesion viva (running/attached/detached) via
    `zellij --session OLD action rename-session NEW`.

    Zellij no permite renombrar sesiones exited; en ese caso devuelve
    "Session 'X' not found" en stderr aunque exit code sea 0. Tratamos
    la presencia de "not found" o "already exists" en la salida como
    fallo.
    """
    if _zellij() is None:
        return False, "zellij is not installed"
    success, out = _run(
        ["zellij", "--session", old_name, "action", "rename-session", new_name],
        timeout=timeout,
    )
    # Aunque el exit code sea 0, zellij puede reportar errores via
    # stderr ("Session 'X' not found", "already exists"). Detectamos
    # esas frases para no mentir al usuario.
    out_lower = out.lower()
    if "not found" in out_lower or "already exists" in out_lower:
        return False, out
    return success, out


def delete_session(
    name: str, *, force: bool = False, timeout: float = 10.0
) -> tuple[bool, str]:
    argv = ["zellij", "delete-session"]
    if force:
        argv.append("-f")
    argv.append(name)
    return _run(argv, timeout=timeout)


def attach_argv(name: str) -> list[str]:
    """Argv para `zellij attach <name>` (resucita si está exited)."""
    return ["zellij", "attach", name]


def new_session_argv(name: str, *, layout: str | None = None) -> list[str]:
    """Argv para crear una sesión. Con layout usa `-n <layout> -s <name>`."""
    if layout:
        return ["zellij", "-n", layout, "-s", name]
    return ["zellij", "-s", name]


def next_default_name(existing: set[str]) -> str:
    """Devuelve un nombre default de una sola palabra, no usado.

    Empieza por `main`, sigue con `main2`, `main3`, ..."""
    if "main" not in existing:
        return "main"
    i = 2
    while f"main{i}" in existing:
        i += 1
    return f"main{i}"


def _run(argv: list[str], *, timeout: float) -> tuple[bool, str]:
    if _zellij() is None:
        return False, "zellij is not installed"
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"command timed out: {' '.join(argv)}"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, _strip_ansi(out).strip()
