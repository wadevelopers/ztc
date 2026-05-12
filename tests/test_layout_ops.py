from __future__ import annotations

from pathlib import Path

from ztc.models.layout import Layout, Pane, Tab
from ztc.zellij import layout_ops


def _layout_with_two_panes() -> Layout:
    return Layout(
        name="test",
        path=Path("/tmp/test.kdl"),
        tabs=[Tab(name="dev", children=[Pane(name="a"), Pane(name="b")])],
    )


def test_is_valid_layout_name() -> None:
    assert layout_ops.is_valid_layout_name("dev")
    assert layout_ops.is_valid_layout_name("dev-trabajo")
    assert layout_ops.is_valid_layout_name("dev_2")
    assert not layout_ops.is_valid_layout_name("dev work")
    assert not layout_ops.is_valid_layout_name("dev/work")
    assert not layout_ops.is_valid_layout_name("")


def test_is_valid_pane_size() -> None:
    assert layout_ops.is_valid_pane_size("")
    assert layout_ops.is_valid_pane_size("60%")
    assert layout_ops.is_valid_pane_size("100%")

    assert not layout_ops.is_valid_pane_size("1")
    assert not layout_ops.is_valid_pane_size("42")
    assert not layout_ops.is_valid_pane_size("0")
    assert not layout_ops.is_valid_pane_size("0%")
    assert not layout_ops.is_valid_pane_size("101%")
    assert not layout_ops.is_valid_pane_size("0.5")
    assert not layout_ops.is_valid_pane_size("ab")
    assert not layout_ops.is_valid_pane_size('"60%"')


def test_new_blank_layout(tmp_path: Path) -> None:
    layout = layout_ops.new_blank_layout(tmp_path, "dev")
    assert layout.name == "dev"
    assert layout.path == tmp_path / "dev.kdl"
    assert len(layout.tabs) == 1
    assert layout.tabs[0].name == "main"
    assert len(layout.tabs[0].children) == 1


def test_add_sibling_inserts_after_target() -> None:
    layout = _layout_with_two_panes()
    target = layout.tabs[0].children[0]
    new_pane = layout_ops.add_sibling(layout, 0, target)
    assert new_pane is not None
    assert layout.tabs[0].children == [target, new_pane, layout.tabs[0].children[2]]


def test_split_pane_creates_container_with_two_children() -> None:
    layout = _layout_with_two_panes()
    target = layout.tabs[0].children[0]
    new_pane = layout_ops.split_pane(layout, 0, target, direction="horizontal")
    assert new_pane is not None

    container = layout.tabs[0].children[0]
    assert container.is_container
    assert container.split_direction == "horizontal"
    assert len(container.children) == 2
    inner_existing, inner_new = container.children
    # Las propiedades de target se han movido al pane interno (excepto size).
    assert inner_existing.name == "a"
    assert inner_new is new_pane
    # El segundo pane original sigue en su sitio.
    assert layout.tabs[0].children[1].name == "b"


def test_split_container_just_appends_child() -> None:
    layout = _layout_with_two_panes()
    container = Pane(split_direction="vertical", children=[Pane(name="x")])
    layout.tabs[0].children = [container]
    new_pane = layout_ops.split_pane(layout, 0, container)
    assert new_pane is not None
    assert container.children[-1] is new_pane


def test_delete_pane_removes_from_parent() -> None:
    layout = _layout_with_two_panes()
    target = layout.tabs[0].children[0]
    assert layout_ops.delete_pane(layout, 0, target) is True
    assert len(layout.tabs[0].children) == 1
    assert layout.tabs[0].children[0].name == "b"


def test_delete_pane_in_nested_tree() -> None:
    inner = Pane(name="inner")
    container = Pane(split_direction="vertical", children=[inner, Pane(name="other")])
    layout = Layout(
        name="t",
        path=Path("/tmp/t.kdl"),
        tabs=[Tab(name="dev", children=[container])],
    )
    assert layout_ops.delete_pane(layout, 0, inner)
    assert len(container.children) == 1
    assert container.children[0].name == "other"


def test_move_pane_swaps_with_neighbor() -> None:
    layout = _layout_with_two_panes()
    a = layout.tabs[0].children[0]
    layout_ops.move_pane(layout, 0, a, delta=1)
    assert [pane.name for pane in layout.tabs[0].children] == ["b", "a"]


def test_move_pane_at_boundary_returns_false() -> None:
    layout = _layout_with_two_panes()
    a = layout.tabs[0].children[0]
    assert layout_ops.move_pane(layout, 0, a, delta=-1) is False
    assert [pane.name for pane in layout.tabs[0].children] == ["a", "b"]


def test_resize_pane_handles_percent_default_and_clamp() -> None:
    pane = Pane()
    assert layout_ops.resize_pane(pane, delta_pct=10) is True
    assert pane.size == "60%"

    pane.size = "90%"
    assert layout_ops.resize_pane(pane, delta_pct=20) is True
    assert pane.size == "95%"  # clamp

    pane.size = "10%"
    assert layout_ops.resize_pane(pane, delta_pct=-10) is True
    assert pane.size == "5%"  # clamp


def test_resize_pane_skips_non_percent() -> None:
    pane = Pane(size="42")
    assert layout_ops.resize_pane(pane, delta_pct=5) is False
    assert pane.size == "42"


def test_replace_pane_keeps_position() -> None:
    layout = _layout_with_two_panes()
    target = layout.tabs[0].children[0]
    replacement = Pane(name="A2", command="echo")
    assert layout_ops.replace_pane(layout, 0, target, replacement)
    assert layout.tabs[0].children[0] is replacement
    assert layout.tabs[0].children[1].name == "b"


def test_enforce_single_pane_focus_clears_siblings_and_nested_panes() -> None:
    focused = Pane(name="focused", focus=True)
    nested = Pane(name="nested", focus=True)
    other_tab_pane = Pane(name="other-tab", focus=True)
    layout = Layout(
        name="x",
        path=Path("/tmp/x.kdl"),
        tabs=[
            Tab(
                name="main",
                children=[
                    Pane(name="old", focus=True),
                    Pane(name="container", focus=True, children=[nested, focused]),
                ],
            ),
            Tab(name="other", children=[other_tab_pane]),
        ],
    )

    assert layout_ops.enforce_single_pane_focus(layout, 0, focused)

    assert focused.focus is True
    assert layout.tabs[0].children[0].focus is False
    assert layout.tabs[0].children[1].focus is False
    assert nested.focus is False
    # La exclusividad es por tab: otros tabs no se tocan.
    assert other_tab_pane.focus is True


def test_enforce_single_pane_focus_returns_false_for_foreign_pane() -> None:
    layout = _layout_with_two_panes()
    foreign = Pane(name="foreign", focus=True)

    assert layout_ops.enforce_single_pane_focus(layout, 0, foreign) is False
    assert foreign.focus is True
    assert [pane.focus for pane in layout.tabs[0].children] == [False, False]


def test_tab_lifecycle() -> None:
    layout = Layout(name="x", path=Path("/tmp/x.kdl"), tabs=[Tab(name="one")])
    layout_ops.add_tab(layout, "two")
    assert [tab.name for tab in layout.tabs] == ["one", "two"]
    layout_ops.rename_tab(layout, 0, "primero")
    assert layout.tabs[0].name == "primero"
    assert layout_ops.delete_tab(layout, 1) is True
    assert [tab.name for tab in layout.tabs] == ["primero"]
    assert layout_ops.delete_tab(layout, 99) is False


def test_split_pane_preserves_default_bg_and_fg() -> None:
    """Cuando se splittea un pane con `default_bg`/`default_fg`, el
    `inner_existing` recreado debe heredar los colores. Sin esto, el
    color "se pierde" visualmente al primer split (queda en el target
    viejo que ya no esta en el arbol)."""
    layout = Layout(
        name="x",
        path=Path("/tmp/x.kdl"),
        tabs=[
            Tab(
                name="t",
                children=[
                    Pane(name="colorful", default_bg="#6272a4", default_fg="#f8f8f2"),
                ],
            )
        ],
    )
    target = layout.tabs[0].children[0]
    new_pane = layout_ops.split_pane(layout, 0, target, direction="vertical")
    assert new_pane is not None

    container = layout.tabs[0].children[0]
    inner_existing = container.children[0]
    assert inner_existing.name == "colorful"
    assert inner_existing.default_bg == "#6272a4"
    assert inner_existing.default_fg == "#f8f8f2"
    # El nuevo pane inserto sin colores propios.
    assert new_pane.default_bg is None
    assert new_pane.default_fg is None
