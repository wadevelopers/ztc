from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ZellijTheme:
    name: str
    builtin: bool = True
