from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# - attached: server vivo + ≥1 cliente conectado (terminal abierta).
# - detached: server vivo + 0 clientes (terminal cerrada sin salir).
# - exited:   server muerto, sesion resurrectable.
# - running:  fallback cuando no se puede determinar attached vs detached
#             (caso degradado; misma semantica que el estado viejo de zsm).
# - unknown:  default antes de listar.
SessionState = Literal["attached", "detached", "running", "exited", "unknown"]


@dataclass
class ZellijSession:
    name: str
    state: SessionState = "unknown"
    raw_line: str | None = None
    attached_clients: int = 0
    """Cuantos clientes estan attacheados a la sesion. 0 si detached
    o no determinable. Solo se llena en estado attached."""
