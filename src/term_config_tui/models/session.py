from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SessionState = Literal["running", "exited", "unknown"]


@dataclass
class ZellijSession:
    name: str
    state: SessionState = "unknown"
    is_current: bool = False
    raw_line: str | None = None
