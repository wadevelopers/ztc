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


# ---------- default_bg / default_fg ----------


def _write_layout(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.kdl"
    p.write_text(content, encoding="utf-8")
    return p


def test_default_bg_fg_property_form_parsed(tmp_path: Path) -> None:
    """Forma propiedad: `pane default_bg="..." default_fg="..."`."""
    p = _write_layout(
        tmp_path,
        '''layout {
    tab name="t" {
        pane default_bg="#6272a4" default_fg="#f8f8f2"
    }
}
''',
    )
    layout = kdl_io.load_layout(p)
    pane = layout.tabs[0].children[0]
    assert pane.default_bg == "#6272a4"
    assert pane.default_fg == "#f8f8f2"


def test_default_bg_fg_child_node_form_parsed(tmp_path: Path) -> None:
    """Forma nodo hijo: `pane { default_bg "..." ; default_fg "..." }`."""
    p = _write_layout(
        tmp_path,
        '''layout {
    tab name="t" {
        pane {
            default_bg "rgb:6c/72/a4"
            default_fg "rgb:f8/f8/f2"
        }
    }
}
''',
    )
    layout = kdl_io.load_layout(p)
    pane = layout.tabs[0].children[0]
    assert pane.default_bg == "rgb:6c/72/a4"
    assert pane.default_fg == "rgb:f8/f8/f2"


def test_default_bg_fg_property_wins_over_child_node(tmp_path: Path) -> None:
    """Cuando ambas formas aparecen, gana la propiedad (espeja el patron
    de command/cwd/size/name en `_apply_child_field`)."""
    p = _write_layout(
        tmp_path,
        '''layout {
    tab name="t" {
        pane default_bg="#aabbcc" default_fg="#001122" {
            default_bg "#999999"
            default_fg "#888888"
        }
    }
}
''',
    )
    layout = kdl_io.load_layout(p)
    pane = layout.tabs[0].children[0]
    assert pane.default_bg == "#aabbcc"
    assert pane.default_fg == "#001122"


def test_dump_emits_default_bg_fg_as_child_nodes(tmp_path: Path) -> None:
    """Forma de emision canonica: child node, no propiedad, tanto si
    el source venia como property como si venia como child node."""
    p = _write_layout(
        tmp_path,
        '''layout {
    tab name="t" {
        pane default_bg="#6272a4" default_fg="#f8f8f2"
    }
}
''',
    )
    layout = kdl_io.load_layout(p)
    text = kdl_io.dump_layout(layout)
    # Emitido como child nodes, NO como propiedades.
    assert 'default_bg "#6272a4"' in text
    assert 'default_fg "#f8f8f2"' in text
    assert 'default_bg=' not in text
    assert 'default_fg=' not in text


def test_dump_pane_with_only_default_bg_keeps_block(tmp_path: Path) -> None:
    """Bug evitado: si un pane tiene SOLO default_bg (sin children/args),
    `has_block` debe seguir abriendo `{...}` para que la directiva no se
    pierda al emitir."""
    layout = Layout(
        name="t",
        path=Path("/tmp/t.kdl"),
        tabs=[Tab(name="t", children=[Pane(default_bg="#6272a4")])],
    )
    text = kdl_io.dump_layout(layout)
    assert '{' in text  # bloque abierto
    assert 'default_bg "#6272a4"' in text


def test_dump_pane_with_only_default_fg_keeps_block(tmp_path: Path) -> None:
    """Mismo bug evitado para el caso de solo default_fg."""
    layout = Layout(
        name="t",
        path=Path("/tmp/t.kdl"),
        tabs=[Tab(name="t", children=[Pane(default_fg="#f8f8f2")])],
    )
    text = kdl_io.dump_layout(layout)
    assert '{' in text
    assert 'default_fg "#f8f8f2"' in text


def test_default_bg_fg_roundtrip_idempotent(tmp_path: Path) -> None:
    """Parse + emit + parse-de-nuevo da el mismo modelo."""
    p = _write_layout(
        tmp_path,
        '''layout {
    tab name="t" {
        pane {
            default_bg "#6272a4"
            default_fg "#f8f8f2"
        }
    }
}
''',
    )
    layout1 = kdl_io.load_layout(p)
    text = kdl_io.dump_layout(layout1)
    p2 = _write_layout(tmp_path / "two", text) if False else None  # noqa
    p2 = tmp_path / "out.kdl"
    p2.write_text(text, encoding="utf-8")
    layout2 = kdl_io.load_layout(p2)
    pane1 = layout1.tabs[0].children[0]
    pane2 = layout2.tabs[0].children[0]
    assert pane1.default_bg == pane2.default_bg == "#6272a4"
    assert pane1.default_fg == pane2.default_fg == "#f8f8f2"
