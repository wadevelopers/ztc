"""Entry point. Corre el TUI; al salir, si el usuario eligió una acción
de lanzamiento (attach/new/bash) hace `os.execvp` al destino."""

from __future__ import annotations

import os
import sys

from ztc.sessions.app import SessionLauncherApp
from ztc.sessions.services import zellij_session


def main() -> None:
    app = SessionLauncherApp()
    app.run()
    target = app.target
    if target is None:
        return  # el usuario salió con q/Esc
    action, payload, extra = target
    if action == "attach":
        argv = zellij_session.attach_argv(payload or "")
        os.execvp(argv[0], argv)
    elif action == "new":
        argv = zellij_session.new_session_argv(payload or "", layout=extra)
        os.execvp(argv[0], argv)
    elif action == "bash":
        shell = os.environ.get("SHELL") or "/bin/bash"
        os.execvp(shell, [shell])
    else:
        sys.exit(f"unknown action: {action}")


if __name__ == "__main__":
    main()
