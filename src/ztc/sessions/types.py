from __future__ import annotations

from typing import Literal

# Acciones que el picker puede pedir al lanzar Zellij. Cualquier otra
# string es invalida y el dispatcher hace `sys.exit` defensivamente.
LaunchAction = Literal["attach", "new", "bash"]

# (action, payload, layout). `payload` = nombre de sesion (attach/new)
# o None (bash). `layout` = nombre de layout (solo para new+layout).
# El tuple completo es None cuando el usuario sale sin elegir nada.
LaunchTarget = tuple[LaunchAction, str | None, str | None] | None
