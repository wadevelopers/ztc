from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ThemeSource = Literal["builtin", "user"]


@dataclass(frozen=True)
class ZellijColor:
    name: str  # ej. "fg", "bg", "red", "text_unselected"
    value: str  # ej. "#cdd6f4" o nombre de color


@dataclass
class ZellijTheme:
    name: str
    source: ThemeSource = "builtin"
    colors: list[ZellijColor] = field(default_factory=list)
    # Componentes del formato nuevo de Zellij (text_unselected, ribbon_*,
    # frame_*, exit_code_*, table_title). Se guardan como kdl.Node opacos
    # para preservarlos exactamente al re-emitir.
    raw_components: list[Any] = field(default_factory=list)

    @property
    def is_user(self) -> bool:
        return self.source == "user"
