"""Entry point. Corre el TUI; al salir, si el usuario eligio una accion
de lanzamiento (attach/new/bash) delega en `launcher.dispatch_target`,
que hace el `os.execvp` cuando Textual ya restauro la terminal."""

from __future__ import annotations

from ztc.sessions import launcher
from ztc.sessions.app import SessionLauncherApp


def main() -> None:
    app = SessionLauncherApp()
    app.run()
    launcher.dispatch_target(app.target)


if __name__ == "__main__":
    main()
