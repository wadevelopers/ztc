from __future__ import annotations

from textual.widgets import Header


class StaticHeader(Header):
    """Header without Textual's click-to-expand behavior."""

    def toggle_class(self, *class_names: str) -> StaticHeader:
        class_names = tuple(name for name in class_names if name != "-tall")
        if class_names:
            super().toggle_class(*class_names)
        return self

    def set_class(
        self,
        add: bool,
        *class_names: str,
        update: bool = True,
    ) -> StaticHeader:
        class_names = tuple(name for name in class_names if name != "-tall")
        if class_names:
            super().set_class(add, *class_names, update=update)
        return self
