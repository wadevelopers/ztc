from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ThemeSource = Literal["builtin", "user"]


@dataclass(frozen=True)
class ZellijColor:
    name: str
    value: str


@dataclass
class ZellijTheme:
    name: str
    source: ThemeSource = "builtin"
    colors: list[ZellijColor] = field(default_factory=list)
    # Bloques anidados del formato nuevo de Zellij (text_selected,
    # ribbon_selected, etc.). Se guardan como kdl.Node opacos para
    # preservarlos exactamente al re-emitir.
    raw_components: list[Any] = field(default_factory=list)

    @property
    def is_user(self) -> bool:
        return self.source == "user"
