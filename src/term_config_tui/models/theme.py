from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

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

    @property
    def is_user(self) -> bool:
        return self.source == "user"
