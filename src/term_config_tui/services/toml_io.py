from __future__ import annotations

from pathlib import Path

import tomlkit
from tomlkit.toml_document import TOMLDocument


def load_toml(path: Path) -> TOMLDocument:
    """Stub Fase 0. La implementacion real va en Fase 0.5."""
    raise NotImplementedError


def dump_toml(doc: TOMLDocument, path: Path) -> None:
    """Stub Fase 0. La implementacion real va en Fase 0.5."""
    raise NotImplementedError


__all__ = ["load_toml", "dump_toml", "tomlkit"]
