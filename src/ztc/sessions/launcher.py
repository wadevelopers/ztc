"""Translates a `LaunchTarget` into the corresponding `os.execvp` call.

The helper exists so both entry points (standalone `zsm` and embedded
`ztc`) share a single dispatch implementation. It must NOT be invoked
from inside a Textual event loop — by construction it is called
*after* `app.run()` returns, when the terminal is back in cooked mode
and the alt-screen has been left. Calling it earlier would leave
zellij with raw mode + alt-screen inherited from Textual, which
locks the host terminal once zellij exits.
"""

from __future__ import annotations

import os
import sys

from ztc.sessions.services.zellij_session import attach_argv, new_session_argv
from ztc.sessions.types import LaunchTarget


def dispatch_target(target: LaunchTarget) -> None:
    if target is None:
        return
    action, payload, extra = target
    if action == "attach":
        argv = attach_argv(payload or "")
        os.execvp(argv[0], argv)
    elif action == "new":
        argv = new_session_argv(payload or "", layout=extra)
        os.execvp(argv[0], argv)
    elif action == "bash":
        shell = os.environ.get("SHELL") or "/bin/bash"
        os.execvp(shell, [shell])
    else:
        # Defense-in-depth. The `LaunchAction` literal already rejects
        # other values at construction time for typed callers; this
        # guards against dynamic data or untyped paths.
        sys.exit(f"unknown action: {action}")
