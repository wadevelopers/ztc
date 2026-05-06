from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def default_zellij_config_dir() -> Path:
    return Path.home() / ".config" / "zellij"


@dataclass
class Paths:
    zellij_config: Path
    zellij_layouts_dir: Path

    @classmethod
    def default(cls) -> Paths:
        zdir = default_zellij_config_dir()
        return cls(
            zellij_config=zdir / "config.kdl",
            zellij_layouts_dir=zdir / "layouts",
        )
