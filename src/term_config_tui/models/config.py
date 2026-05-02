from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def default_zellij_config_dir() -> Path:
    return Path.home() / ".config" / "zellij"


def default_alacritty_config_dir() -> Path:
    return Path.home() / ".config" / "alacritty"


@dataclass
class Paths:
    zellij_config: Path
    zellij_layouts_dir: Path
    alacritty_config: Path

    @classmethod
    def default(cls) -> "Paths":
        zdir = default_zellij_config_dir()
        return cls(
            zellij_config=zdir / "config.kdl",
            zellij_layouts_dir=zdir / "layouts",
            alacritty_config=default_alacritty_config_dir() / "alacritty.toml",
        )
