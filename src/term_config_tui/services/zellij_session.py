from __future__ import annotations

import os
import re
import shutil
import subprocess

from term_config_tui.models.session import ZellijSession

# Zellij prefija escapes ANSI cuando -n no se usa, y a veces aun con -n.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_NO_SESSIONS = re.compile(r"no active.*sessions", re.IGNORECASE)


def is_inside_zellij() -> bool:
    return bool(os.environ.get("ZELLIJ"))


def current_session_name() -> str | None:
    return os.environ.get("ZELLIJ_SESSION_NAME")


def _strip_ansi(s: str) -> str:
    return _ANSI.sub("", s)


def _zellij() -> str | None:
    return shutil.which("zellij")


def list_sessions(*, timeout: float = 5.0) -> list[ZellijSession]:
    """Lista sesiones via `zellij list-sessions -n`. Devuelve [] si no hay ninguna.

    Cada linea tipica:
        main [Created 14m 4s ago]
    o (sesiones salidas en versiones que lo soportan):
        EXITED - old [...]
    """
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
    current = current_session_name()
    for raw in combined.splitlines():
        line = _strip_ansi(raw).strip()
        if not line:
            continue
        if _NO_SESSIONS.search(line):
            continue
        session = _parse_line(line)
        if session is None:
            continue
        if current and session.name == current:
            session.is_current = True
        out.append(session)
    return out


def _parse_line(line: str) -> ZellijSession | None:
    """Saca nombre y estado de una linea de `list-sessions`.

    Acepta:
      - 'name [Created 14m 4s ago]' -> running
      - 'name [Created ... ago] (current)' -> running
      - 'EXITED - name [...]'  -> exited
      - 'name'  (formato `-s`) -> running por defecto
    """
    m = re.match(r"^EXITED\s*-\s*(?P<name>\S+)(?:\s+(?P<rest>.*))?$", line)
    if m:
        return ZellijSession(
            name=m.group("name"),
            state="exited",
            raw_line=line,
        )
    m = re.match(r"^(?P<name>\S+)(?:\s+(?P<rest>.*))?$", line)
    if m:
        return ZellijSession(
            name=m.group("name"),
            state="running",
            raw_line=line,
        )
    return None


def kill_session(name: str, *, timeout: float = 10.0) -> tuple[bool, str]:
    """Mata una sesion viva. Devuelve (ok, output_combinado)."""
    return _run(["zellij", "kill-session", name], timeout=timeout)


def delete_session(name: str, *, force: bool = False, timeout: float = 10.0) -> tuple[bool, str]:
    """Borra una sesion. Si force, anade -f para matarla si esta viva."""
    argv = ["zellij", "delete-session"]
    if force:
        argv.append("-f")
    argv.append(name)
    return _run(argv, timeout=timeout)


def attach_argv(name: str) -> list[str]:
    """Argv para hacer `zellij attach` desde un contexto que toma la TTY (suspend)."""
    return ["zellij", "attach", name]


def new_session_argv(name: str, *, layout: str | None = None) -> list[str]:
    """Argv para crear una sesion. Si layout, usa `-n <layout> -s <name>`.

    -n siempre crea una sesion nueva, incluso si ya estamos dentro de otra,
    aunque normalmente el flujo es desde fuera.
    """
    if layout:
        return ["zellij", "-n", layout, "-s", name]
    return ["zellij", "-s", name]


def _run(argv: list[str], *, timeout: float) -> tuple[bool, str]:
    if _zellij() is None:
        return False, "zellij no esta instalado"
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"comando excedio el timeout: {' '.join(argv)}"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, _strip_ansi(out).strip()
