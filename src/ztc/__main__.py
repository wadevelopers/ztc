"""Entry point. Corre el TUI; al salir, si el usuario eligio una accion
del launcher embebido (attach/new/bash desde "Zellij sessions"),
delega en `launcher.dispatch_target`. El `execvp` ocurre **despues**
que `app.run()` retorna para que Textual haya restaurado el estado de
la terminal — sin eso, zellij hereda raw mode + alt-screen y la
terminal queda bloqueada al salir."""

from __future__ import annotations

from ztc.app import TermConfigApp
from ztc.sessions import launcher


def main() -> None:
    app = TermConfigApp()
    app.run()
    launcher.dispatch_target(app.pending_launch)


if __name__ == "__main__":
    main()
