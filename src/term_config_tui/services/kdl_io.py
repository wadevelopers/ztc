from __future__ import annotations

from pathlib import Path

from term_config_tui.models.layout import Layout, Pane, SplitDirection, Tab


def load_layout(path: Path) -> Layout:
    """Stub Fase 0. La implementacion real va en Fase 0.5."""
    raise NotImplementedError


def dump_layout(layout: Layout) -> str:
    """Stub Fase 0. La implementacion real va en Fase 0.5."""
    raise NotImplementedError


__all__ = ["Layout", "Pane", "Tab", "SplitDirection", "load_layout", "dump_layout"]
