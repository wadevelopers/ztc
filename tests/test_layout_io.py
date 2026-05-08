from __future__ import annotations

from pathlib import Path

from ztc.models.layout import Layout, Pane, Tab
from ztc.zellij import layout_io as kdl_io

FIX = Path(__file__).parent / "fixtures" / "zellij"


def test_load_simple_layout_parses_tabs_and_panes() -> None:
    layout = kdl_io.load_layout(FIX / "layout_simple.kdl")
    assert layout.name == "layout_simple"
    assert len(layout.tabs) == 2
    system, dev = layout.tabs

    assert system.name == "system"
    assert len(system.children) == 1
    leaf = system.children[0]
    assert leaf.command == "btop"
    assert leaf.start_suspended is True

    assert dev.name == "dev"
    assert len(dev.children) == 1
    container = dev.children[0]
    assert container.split_direction == "vertical"
    assert len(container.children) == 2
    left, right = container.children
    assert left.size == "60%"
    assert len(left.children) == 3
    assert right.size == "40%"
    assert right.children == []


def test_load_real_dev_layout_does_not_crash() -> None:
    real = Path.home() / ".config" / "zellij" / "layouts" / "dev.kdl"
    if not real.exists():
        return  # entorno sin layouts reales, no es un fallo
    layout = kdl_io.load_layout(real)
    # Aunque el layout real tiene `default_tab_template`, debemos haber
    # extraido al menos las tabs.
    assert any(tab.name in {"system", "dev"} for tab in layout.tabs)


def test_dump_layout_minimal_roundtrip() -> None:
    layout = Layout(
        name="dev",
        path=Path("/tmp/dev.kdl"),
        tabs=[
            Tab(
                name="system",
                children=[
                    Pane(command="btop", start_suspended=True),
                ],
            ),
            Tab(
                name="dev",
                children=[
                    Pane(
                        split_direction="vertical",
                        children=[
                            Pane(size="60%"),
                            Pane(size="40%"),
                        ],
                    )
                ],
            ),
        ],
    )
    text = kdl_io.dump_layout(layout)
    # Debe ser KDL valido segun kdl-py.
    import kdl

    parsed = kdl.parse(text)
    assert parsed.nodes[0].name == "layout"

    # Re-cargar usando nuestro loader sobre un fichero temporal y comprobar igualdad.
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".kdl", delete=False) as fh:
        fh.write(text)
        path = Path(fh.name)
    try:
        again = kdl_io.load_layout(path)
        assert [tab.name for tab in again.tabs] == ["system", "dev"]
        assert again.tabs[0].children[0].command == "btop"
        assert again.tabs[0].children[0].start_suspended is True
        assert again.tabs[1].children[0].split_direction == "vertical"
        assert again.tabs[1].children[0].children[0].size == "60%"
        assert again.tabs[1].children[0].children[1].size == "40%"
    finally:
        path.unlink(missing_ok=True)


def test_dump_preserves_layout_raw_nodes(tmp_path: Path) -> None:
    src = tmp_path / "with_template.kdl"
    src.write_text(
        'layout {\n'
        '    default_tab_template {\n'
        '        pane size=1 borderless=true {\n'
        '            plugin location="zellij:status-bar"\n'
        '        }\n'
        '        children\n'
        '    }\n'
        '    tab name="dev" {\n'
        '        pane\n'
        '    }\n'
        '}\n',
        encoding="utf-8",
    )
    layout = kdl_io.load_layout(src)
    assert len(layout.raw_unknown_nodes) == 1
    text = kdl_io.dump_layout(layout)
    assert "default_tab_template" in text
    assert "zellij:status-bar" in text
    assert 'tab name="dev"' in text


def test_dump_preserves_pane_raw_nodes(tmp_path: Path) -> None:
    src = tmp_path / "panes_with_plugin.kdl"
    src.write_text(
        'layout {\n'
        '    tab {\n'
        '        pane {\n'
        '            plugin location="zellij:strider"\n'
        '        }\n'
        '    }\n'
        '}\n',
        encoding="utf-8",
    )
    layout = kdl_io.load_layout(src)
    text = kdl_io.dump_layout(layout)
    assert "zellij:strider" in text


def test_dump_layout_emits_no_default_props() -> None:
    layout = Layout(name="x", path=Path("/tmp/x.kdl"), tabs=[Tab(name="t")])
    text = kdl_io.dump_layout(layout)
    # focus=False y borderless=False no deben aparecer.
    assert "focus=" not in text
    assert "borderless=" not in text
    assert "start_suspended=" not in text
