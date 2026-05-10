from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

SplitDirection = Literal["vertical", "horizontal"]


@dataclass(eq=False)
class Pane:
    command: str | None = None
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    start_suspended: bool = False
    size: str | None = None
    focus: bool = False
    name: str | None = None
    borderless: bool = False
    default_bg: str | None = None
    default_fg: str | None = None
    children: list[Pane] = field(default_factory=list)
    split_direction: SplitDirection | None = None
    raw_unknown_nodes: list[Any] = field(default_factory=list)

    @property
    def is_container(self) -> bool:
        return bool(self.children)


@dataclass(eq=False)
class Tab:
    name: str | None = None
    children: list[Pane] = field(default_factory=list)
    focus: bool = False
    cwd: str | None = None
    split_direction: SplitDirection | None = None
    raw_unknown_nodes: list[Any] = field(default_factory=list)


@dataclass
class Layout:
    name: str
    path: Path
    tabs: list[Tab] = field(default_factory=list)
    cwd: str | None = None
    raw_unknown_nodes: list[Any] = field(default_factory=list)
