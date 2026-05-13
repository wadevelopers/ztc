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

# Path del socket de Zellij dentro de un dir de sesion. El nombre de
# sesion es el ultimo componente del path; puede tener espacios pero no
# `/`. Se ancla a fin de string porque se aplica al path ya aislado de
# la linea de `ss -xa` (ver _parse_ss_unix_lines).
_ZELLIJ_SOCKET_PATH_RE = re.compile(
    r"/zellij/contract_version_\d+/(?P<name>[^/]+)$"
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

    Para cada proceso `zellij` cliente (no `--server`) se determina su
    sesion: primero siguiendo el socket UNIX hacia el server (`ss -xa`
    + `/proc/PID/fd`), que es autoritativo y cubre tambien `zellij`
    pelado; si eso no resuelve, se mira el argv del cliente
    (`attach NAME`, `-s NAME`, ...). El argv se lee de
    `/proc/PID/cmdline` (separado por NUL) para preservar nombres de
    sesion con espacios.

    Devuelve `None` si `pgrep` no esta disponible o falla; el caller
    interpreta `None` como "no se pudo determinar" y deja las sesiones
    como `running` (estado fallback)."""
    if shutil.which("pgrep") is None:
        return None
    try:
        proc = subprocess.run(
            ["pgrep", "-x", "zellij"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None

    inode_to_session = _build_inode_session_map(timeout=timeout)

    counts: dict[str, int] = {}
    for raw_pid in (proc.stdout or "").split():
        try:
            pid = int(raw_pid)
        except ValueError:
            continue
        argv = _proc_cmdline(pid)
        if not argv:
            continue
        # Solo clientes: excluimos servers y binarios que no sean `zellij`.
        if "--server" in argv:
            continue
        if argv[0].rsplit("/", 1)[-1] != "zellij":
            continue

        name = _session_via_sockets(pid, inode_to_session)
        if name is None:
            name = _session_name_from_argv(argv)
        if name:
            counts[name] = counts.get(name, 0) + 1

    return counts


def _proc_cmdline(pid: int) -> list[str] | None:
    """Lee `/proc/<pid>/cmdline` (argumentos separados por NUL) y los
    devuelve como lista. `None` si no se puede leer (proceso terminado,
    sin permisos) o si esta vacio (proceso kernel)."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return None
    parts = raw.split(b"\0")
    # /proc/<pid>/cmdline suele terminar en NUL -> ultimo elemento vacio.
    while parts and parts[-1] == b"":
        parts.pop()
    if not parts:
        return None
    return [p.decode("utf-8", "surrogateescape") for p in parts]


def _build_inode_session_map(*, timeout: float = 2.0) -> dict[int, str]:
    """Corre `ss -xa` y devuelve {client_peer_inode: session_name} (ver
    `_parse_ss_unix_lines`). Vacio si `ss` no esta o falla."""
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
    return _parse_ss_unix_lines(proc.stdout or "")


def _parse_ss_unix_lines(text: str) -> dict[int, str]:
    """Mapea {client_peer_inode: session_name} a partir de la salida de
    `ss -xa`.

    Para una conexion cliente<->server de Zellij, el socket aceptado por
    el server aparece como una linea ESTAB cuyo "Local Address:Port" es
    `<path> <inode>` (el path puede tener espacios) y cuyo "Peer
    Address:Port" es `* <client_inode>` (el cliente es anonimo). Por eso
    el path local es `fields[4:-3]` unido por espacio, el client inode es
    `fields[-1]`, y `fields[-2]` debe ser `*`. Despues, leyendo
    `/proc/PID/fd` de un cliente, si alguno de sus sockets matchea una
    key de este map, sabemos a que sesion esta attached."""
    out: dict[int, str] = {}
    for line in text.splitlines():
        if "ESTAB" not in line or "/zellij/" not in line:
            continue
        fields = line.split()
        if len(fields) < 8 or fields[-2] != "*":
            continue
        local_addr = " ".join(fields[4:-3])
        m = _ZELLIJ_SOCKET_PATH_RE.search(local_addr)
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


def _session_name_from_argv(argv: list[str]) -> str | None:
    """Extrae el nombre de sesion del argv de un cliente `zellij`.

    Reconoce las formas con que zsm y los usuarios lo lanzan:
    - opciones globales `-s NAME` / `-sNAME` / `--session NAME` /
      `--session=NAME`
    - subcommand `attach NAME` / `a NAME` (NAME = primer arg que no
      empieza con `-` despues del subcommand)

    `None` si ninguna aplica (`zellij` pelado, `zellij options ...`,
    `zellij attach --index N`, ...) — el caller cae a la deteccion por
    socket, que es autoritativa."""
    args = argv[1:]
    for i, tok in enumerate(args):
        if tok in ("-s", "--session"):
            return args[i + 1] if i + 1 < len(args) else None
        if tok.startswith("--session="):
            return tok[len("--session=") :] or None
        if tok.startswith("-s") and not tok.startswith("--") and len(tok) > 2:
            return tok[2:]
        if tok in ("attach", "a"):
            for sub in args[i + 1 :]:
                if not sub.startswith("-"):
                    return sub
            return None
    return None


def _parse_line(line: str) -> ZellijSession | None:
    """Saca nombre y estado de una linea de `zellij list-sessions -n`.

    Formato actual: `<name> [Created <dur> ago]<sufijo>`, donde el
    sufijo opcional es ` (current)` o ` (EXITED - attach to resurrect)`.
    El nombre puede contener espacios (Zellij los permite), asi que se
    corta en ` [Created `, no en el primer whitespace.

    Tambien se tolera el formato legacy `EXITED - <name> [Created ...]`.
    """
    rest = line
    forced_exited = False
    legacy = re.match(r"^EXITED\s*-\s*(?P<rest>.+)$", line)
    if legacy:
        rest = legacy.group("rest")
        forced_exited = True

    marker = rest.find(" [Created ")
    if marker >= 0:
        name, tail = rest[:marker].strip(), rest[marker:]
    else:
        name, tail = rest.strip(), ""
    if not name:
        return None

    state = (
        "exited" if forced_exited or _EXITED_SUFFIX.search(tail) else "running"
    )
    return ZellijSession(name=name, state=state, raw_line=line)


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
