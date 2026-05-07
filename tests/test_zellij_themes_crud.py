"""Tests del CRUD de user themes (splice del bloque themes)."""

from __future__ import annotations

from pathlib import Path

import pytest

from zellij_themes.models import ZellijColor, ZellijTheme
from ztc.services import zellij_themes
from ztc.services.terminals.alacritty import AlacrittyBackend


def test_parser_captures_raw_components(tmp_path: Path) -> None:
    """Bloques anidados en un user theme (formato nuevo) se preservan en
    raw_components."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n'
        '    mio {\n'
        '        fg "#cdd6f4"\n'
        '        bg "#1e1e2e"\n'
        '        text_selected {\n'
        '            base "#aaaaaa"\n'
        '            background "#585b70"\n'
        '        }\n'
        '        ribbon_selected {\n'
        '            background "#a6e3a1"\n'
        '        }\n'
        '    }\n'
        '}\n',
        encoding="utf-8",
    )
    themes = zellij_themes.list_user_themes(cfg)
    assert len(themes) == 1
    t = themes[0]
    # Slots legacy se siguen capturando.
    assert {c.name for c in t.colors} == {"fg", "bg"}
    # raw_components contiene los bloques anidados.
    assert len(t.raw_components) == 2
    component_names = {rc.name for rc in t.raw_components}
    assert component_names == {"text_selected", "ribbon_selected"}


def test_renderer_emits_raw_components(tmp_path: Path) -> None:
    """Round-trip: parsear un theme con raw_components y re-emitirlo
    debe preservar los bloques anidados."""
    cfg = tmp_path / "config.kdl"
    original = (
        'themes {\n'
        '    mio {\n'
        '        fg "#cdd6f4"\n'
        '        bg "#1e1e2e"\n'
        '        text_selected {\n'
        '            base "#aaaaaa"\n'
        '            background "#585b70"\n'
        '        }\n'
        '    }\n'
        '}\n'
    )
    cfg.write_text(original, encoding="utf-8")
    themes = zellij_themes.list_user_themes(cfg)
    rendered = zellij_themes.render_themes_block(themes)
    # El render debe contener tanto slots legacy como bloque rich.
    assert 'fg "#cdd6f4"' in rendered
    assert "text_selected {" in rendered
    assert 'base "#aaaaaa"' in rendered
    assert 'background "#585b70"' in rendered


def test_renderer_converts_rgb_triples_to_hex(tmp_path: Path) -> None:
    """RGB triples del formato nuevo (`base 255 200 100`) se convierten
    a hex string (`base "#ffc864"`) al re-emitir."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n'
        '    mio {\n'
        '        text_selected {\n'
        '            base 255 200 100\n'
        '            background 88 91 112\n'
        '        }\n'
        '    }\n'
        '}\n',
        encoding="utf-8",
    )
    themes = zellij_themes.list_user_themes(cfg)
    rendered = zellij_themes.render_themes_block(themes)
    assert '"#ffc864"' in rendered
    assert '"#585b70"' in rendered
    # Sin sufijos float ni triples sueltos.
    assert "255.0" not in rendered
    assert "255 200 100" not in rendered


def test_get_set_unset_rich_slot() -> None:
    """Helpers para manipular slots ricos del theme."""
    t = ZellijTheme(name="test", source="user")
    # Set crea el componente desde cero
    zellij_themes.set_rich_slot(t, "text_selected", "background", "#5566aa")
    assert zellij_themes.get_rich_slot(t, "text_selected", "background") == "#5566aa"
    # Set en componente existente agrega slot nuevo
    zellij_themes.set_rich_slot(t, "text_selected", "base", "#ffffff")
    assert zellij_themes.get_rich_slot(t, "text_selected", "base") == "#ffffff"
    # Set sobre slot existente actualiza
    zellij_themes.set_rich_slot(t, "text_selected", "background", "#aabbcc")
    assert zellij_themes.get_rich_slot(t, "text_selected", "background") == "#aabbcc"
    # Get inexistente devuelve None
    assert zellij_themes.get_rich_slot(t, "foo", "bar") is None
    # Unset elimina el slot
    zellij_themes.unset_rich_slot(t, "text_selected", "background")
    assert zellij_themes.get_rich_slot(t, "text_selected", "background") is None
    # base sigue ahi
    assert zellij_themes.get_rich_slot(t, "text_selected", "base") == "#ffffff"
    # Unset del ultimo slot elimina la componente entera
    zellij_themes.unset_rich_slot(t, "text_selected", "base")
    assert len(t.raw_components) == 0


def test_save_round_trip_preserves_rich_overrides(tmp_path: Path) -> None:
    """Bajo Option C, guardar un theme con un slot rico expande a las 6
    componentes activas (text_*, ribbon_*, frame_*) con derivacion + el
    override del usuario. El override puntual se preserva exactamente."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        '// header\n'
        'themes {\n'
        '    mio {\n'
        '        fg "#fff"\n'
        '        text_selected {\n'
        '            base "#aaa"\n'
        '            background "#222222"\n'
        '        }\n'
        '    }\n'
        '}\n',
        encoding="utf-8",
    )
    themes = zellij_themes.list_user_themes(cfg)
    zellij_themes.save_user_themes(cfg, themes, backup=False)
    themes_again = zellij_themes.list_user_themes(cfg)
    assert len(themes_again) == 1
    component_names = {rc.name for rc in themes_again[0].raw_components}
    assert "text_selected" in component_names
    assert "ribbon_selected" in component_names
    assert "frame_selected" in component_names
    # El override puntual del usuario sobrevive al round-trip.
    assert (
        zellij_themes.get_rich_slot(themes_again[0], "text_selected", "background")
        == "#222222"
    )


def test_is_valid_theme_name() -> None:
    assert zellij_themes.is_valid_theme_name("dracula")
    assert zellij_themes.is_valid_theme_name("custom_dark")
    assert zellij_themes.is_valid_theme_name("my-theme-2")
    assert not zellij_themes.is_valid_theme_name("2bad")  # empieza por digito
    assert not zellij_themes.is_valid_theme_name("with space")
    assert not zellij_themes.is_valid_theme_name("")


def test_find_themes_block_handles_nested_braces() -> None:
    text = (
        "keybinds {}\n"
        "themes {\n"
        '    a {\n        fg "#fff"\n    }\n'
        '    b {\n'
        '        bg "#000"\n'
        "    }\n"
        "}\n"
        'theme "a"\n'
    )
    rng = zellij_themes.find_themes_block(text)
    assert rng is not None
    start, end = rng
    block = text[start:end]
    assert block.startswith("themes {")
    assert block.endswith("}")
    assert 'fg "#fff"' in block
    assert 'theme "a"' not in block  # no debe extenderse


def test_find_themes_block_returns_none_when_missing() -> None:
    assert zellij_themes.find_themes_block("// no themes here\n") is None


def test_find_themes_block_handles_brace_in_string() -> None:
    text = 'themes {\n    a { fg "#}{ raro }" }\n}\n'
    rng = zellij_themes.find_themes_block(text)
    assert rng is not None
    start, end = rng
    assert text[start:end].endswith("}")
    # Y solo el bloque themes, sin texto extra.
    assert text[end:].strip() == ""


def test_render_themes_block_format() -> None:
    """Modo always-save: cada tema emite legacy + las 7 componentes ricas."""
    themes = [
        ZellijTheme(
            name="t1",
            source="user",
            colors=[ZellijColor("fg", "#fff"), ZellijColor("bg", "#000")],
        )
    ]
    text = zellij_themes.render_themes_block(themes)
    assert text.startswith('themes {\n    t1 {\n        fg "#fff"\n        bg "#000"\n')
    # Las 7 componentes activas presentes.
    for comp in (
        "text_unselected",
        "text_selected",
        "ribbon_unselected",
        "ribbon_selected",
        "frame_unselected",
        "frame_selected",
        "frame_highlight",
    ):
        assert f"{comp} {{" in text


def test_save_user_themes_replaces_existing_block(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        '// header\n'
        'keybinds {\n    normal {}\n}\n'
        'themes {\n'
        '    old {\n        fg "#ff0000"\n    }\n'
        '}\n'
        'theme "old"\n',
        encoding="utf-8",
    )
    new = [
        ZellijTheme(
            name="new",
            source="user",
            colors=[ZellijColor("fg", "#abcdef"), ZellijColor("bg", "#111111")],
        )
    ]
    backup = zellij_themes.save_user_themes(cfg, new)
    text = cfg.read_text(encoding="utf-8")
    # Bloque viejo desaparece, bloque nuevo presente.
    assert "old {" not in text
    assert "new {" in text
    assert 'fg "#abcdef"' in text
    # Resto preservado.
    assert "// header" in text
    assert "keybinds {" in text
    assert 'theme "old"' in text  # la directiva es ortogonal al bloque
    # Backup creado.
    assert backup is not None and backup.exists()


def test_save_user_themes_appends_when_no_block(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text("default_mode \"normal\"\n", encoding="utf-8")
    themes = [
        ZellijTheme(
            name="t",
            source="user",
            colors=[ZellijColor("bg", "#000000")],
        )
    ]
    zellij_themes.save_user_themes(cfg, themes)
    text = cfg.read_text(encoding="utf-8")
    assert text.startswith('default_mode "normal"')
    assert "themes {" in text
    assert "t {" in text


def test_save_user_themes_empty_list_removes_block(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'keybinds {}\n\nthemes {\n    a {\n        fg "#000"\n    }\n}\n\ndefault_mode "normal"\n',
        encoding="utf-8",
    )
    zellij_themes.save_user_themes(cfg, [])
    text = cfg.read_text(encoding="utf-8")
    assert "themes {" not in text
    assert "keybinds {}" in text
    assert 'default_mode "normal"' in text


def test_upsert_user_theme_adds_then_updates(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    zellij_themes.upsert_user_theme(
        cfg,
        ZellijTheme(name="a", source="user", colors=[ZellijColor("fg", "#111")]),
    )
    themes = zellij_themes.list_user_themes(cfg)
    assert [t.name for t in themes] == ["a"]
    # Update: cambiar el color.
    zellij_themes.upsert_user_theme(
        cfg,
        ZellijTheme(name="a", source="user", colors=[ZellijColor("fg", "#222")]),
    )
    themes = zellij_themes.list_user_themes(cfg)
    assert themes[0].colors[0].value == "#222"


def test_delete_user_theme_removes_only_target(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n'
        '    a {\n        fg "#000"\n    }\n'
        '    b {\n        fg "#fff"\n    }\n'
        '}\n',
        encoding="utf-8",
    )
    zellij_themes.delete_user_theme(cfg, "a")
    themes = zellij_themes.list_user_themes(cfg)
    assert [t.name for t in themes] == ["b"]


def test_delete_user_theme_no_op_when_missing(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n    a {\n        fg "#000"\n    }\n}\n',
        encoding="utf-8",
    )
    backup = zellij_themes.delete_user_theme(cfg, "nope")
    assert backup is None  # no se hizo escritura


def test_clone_user_theme_copies_colors(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n    src {\n        fg "#abc"\n    }\n}\n',
        encoding="utf-8",
    )
    zellij_themes.clone_theme(cfg, "src", "dst")
    themes = {t.name: t for t in zellij_themes.list_user_themes(cfg)}
    assert "dst" in themes
    assert themes["dst"].colors[0].value == "#abc"


def test_clone_builtin_extracts_colors_from_bundled(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    # 'dracula' es built-in vendorizado: clonar extrae slots legacy
    # desde los componentes UI del .kdl bundled aplicando la regla unica.
    zellij_themes.clone_theme(cfg, "dracula", "my-dracula")
    themes = zellij_themes.list_user_themes(cfg)
    assert themes[0].name == "my-dracula"
    by_name = {c.name: c.value for c in themes[0].colors}
    assert list(by_name.keys()) == list(zellij_themes.LEGACY_SLOTS)
    # fg de dracula = ribbon_unselected.background = #f8f8f2.
    assert by_name["fg"] == "#f8f8f2"
    # bg de dracula = text_unselected.background = #000000 (sin override).
    assert by_name["bg"] == "#000000"
    # red = exit_code_error.base = #ff5555.
    assert by_name["red"] == "#ff5555"


def test_clone_ayu_dark_bg_is_text_unselected(tmp_path: Path) -> None:
    """Regresion: ayu-dark stores el bg real en text_unselected.background
    (#131721), no en text_selected.background (#475266 = pane seleccionado)."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    zellij_themes.clone_theme(cfg, "ayu-dark", "my-ayu")
    by_name = {c.name: c.value for c in zellij_themes.list_user_themes(cfg)[0].colors}
    assert by_name["bg"] == "#131721"


def test_clone_active_theme_overlays_alacritty(tmp_path: Path) -> None:
    """Cuando se clona el tema activo y hay alacritty.toml, los slots
    actuales de alacritty deben pisar a los derivados del .kdl."""
    # Configurar: tema activo = dracula.
    cfg = tmp_path / "config.kdl"
    cfg.write_text('theme "dracula"\n', encoding="utf-8")

    # Alacritty con valores tweakeados (distintos al derivado de dracula).
    ala = tmp_path / "alacritty.toml"
    ala.write_text(
        "[colors.primary]\n"
        'background = "#222222"\n'
        'foreground = "#eeeeee"\n'
        "\n[colors.normal]\n"
        'red = "#ff0000"\n'
        'green = "#00ff00"\n',
        encoding="utf-8",
    )

    zellij_themes.clone_theme(
        cfg, "dracula", "my-dracula",
        backend=AlacrittyBackend(), backend_path=ala,
    )
    by_name = {
        c.name: c.value for c in zellij_themes.list_user_themes(cfg)[0].colors
    }
    # Mapping 1:1: primary.foreground -> fg, primary.background -> bg.
    assert by_name["bg"] == "#222222"
    assert by_name["fg"] == "#eeeeee"
    assert by_name["red"] == "#ff0000"
    assert by_name["green"] == "#00ff00"
    # Los slots NO presentes en alacritty quedan del derivado del .kdl.
    assert by_name["yellow"] != "#000000"


def test_clone_non_active_theme_ignores_alacritty(tmp_path: Path) -> None:
    """Si se clona un tema que NO es el activo, alacritty no aplica
    porque alacritty representa OTRO tema en ese momento."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text('theme "dracula"\n', encoding="utf-8")
    ala = tmp_path / "alacritty.toml"
    ala.write_text(
        "[colors.primary]\n"
        'background = "#222222"\n'
        'foreground = "#eeeeee"\n',
        encoding="utf-8",
    )
    # Cloneamos tokyo-night (NO es el activo).
    zellij_themes.clone_theme(
        cfg, "tokyo-night", "my-tn",
        backend=AlacrittyBackend(), backend_path=ala,
    )
    by_name = {
        c.name: c.value for c in zellij_themes.list_user_themes(cfg)[0].colors
    }
    # Debe coger los del .kdl de tokyo-night, NO los de alacritty.
    assert by_name["bg"] != "#222222"
    assert by_name["fg"] != "#eeeeee"


def test_clone_active_user_theme_overlays_alacritty(tmp_path: Path) -> None:
    """El overlay tambien aplica cuando el activo es un user theme."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n    mio {\n        fg "#aaaaaa"\n        bg "#111111"\n    }\n}\n'
        'theme "mio"\n',
        encoding="utf-8",
    )
    ala = tmp_path / "alacritty.toml"
    ala.write_text(
        '[colors.primary]\nbackground = "#222222"\nforeground = "#eeeeee"\n',
        encoding="utf-8",
    )
    zellij_themes.clone_theme(
        cfg, "mio", "mio-copia",
        backend=AlacrittyBackend(), backend_path=ala,
    )
    themes = zellij_themes.list_user_themes(cfg)
    clone = next(t for t in themes if t.name == "mio-copia")
    by_name = {c.name: c.value for c in clone.colors}
    assert by_name["bg"] == "#222222"
    # Mapping 1:1: primary.foreground -> fg.
    assert by_name["fg"] == "#eeeeee"


def test_clone_without_backend_uses_kdl_only(tmp_path: Path) -> None:
    """Sin backend, comportamiento clasico: solo .kdl."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text('theme "dracula"\n', encoding="utf-8")
    zellij_themes.clone_theme(cfg, "dracula", "my-dracula")
    by_name = {
        c.name: c.value for c in zellij_themes.list_user_themes(cfg)[0].colors
    }
    # Sin override de dracula bg, queda como text_unselected.background = #000000.
    assert by_name["bg"] == "#000000"
    assert by_name["fg"] == "#f8f8f2"


def test_clone_builtin_preserves_rich_components(tmp_path: Path) -> None:
    """Al clonar un built-in se emiten las 6 componentes activas
    (text_*, ribbon_*, frame_*) tomando los valores hand-tuned del .kdl
    bundled como override sobre la derivacion legacy. Los componentes
    obscuros (table_*, list_*, exit_code_*, multiplayer_*) no se vuelcan."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    zellij_themes.clone_theme(cfg, "molokai-dark", "my-molokai")
    text = cfg.read_text(encoding="utf-8")
    # Las 6 componentes activas presentes.
    assert "text_unselected {" in text
    assert "text_selected {" in text
    assert "ribbon_unselected {" in text
    assert "ribbon_selected {" in text
    assert "frame_selected {" in text
    assert "frame_highlight {" in text
    # ribbon_selected.background de molokai (#008c00) preservado.
    assert '"#008c00"' in text
    # Componentes no activos no se emiten.
    assert "table_title" not in text
    assert "list_unselected" not in text
    assert "multiplayer_user_colors" not in text


def test_clone_user_theme_preserves_rich_components(tmp_path: Path) -> None:
    """Si el src es un user theme con raw_components, el clone tambien
    los preserva (clone de clone)."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    zellij_themes.clone_theme(cfg, "dracula", "my-dracula")
    zellij_themes.clone_theme(cfg, "my-dracula", "my-dracula-2")
    themes = {t.name: t for t in zellij_themes.list_user_themes(cfg)}
    assert "my-dracula-2" in themes
    component_names = {rc.name for rc in themes["my-dracula-2"].raw_components}
    assert "text_selected" in component_names
    assert "ribbon_selected" in component_names


def test_clone_unknown_uses_black_defaults(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    # Theme name desconocido (no built-in, no user) -> defaults #000000.
    zellij_themes.clone_theme(cfg, "totally-fake-theme", "copy")
    themes = zellij_themes.list_user_themes(cfg)
    assert themes[0].colors[0].value == "#000000"


def test_clone_rejects_existing_name(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n    foo {\n        fg "#000"\n    }\n}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        zellij_themes.clone_theme(cfg, "foo", "foo")


def test_clone_rejects_invalid_name(tmp_path: Path) -> None:
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    with pytest.raises(ValueError):
        zellij_themes.clone_theme(cfg, "dracula", "1invalid")


def test_render_always_emits_legacy_plus_rich(tmp_path: Path) -> None:
    """Modo always-save: cualquier tema emite legacy + 7 componentes ricas
    aunque no tenga raw_components. Los slots ricos vienen de la
    derivacion desde el legacy."""
    themes = [
        ZellijTheme(
            name="t",
            source="user",
            colors=[
                ZellijColor("fg", "#aabbcc"),
                ZellijColor("bg", "#112233"),
            ],
        )
    ]
    text = zellij_themes.render_themes_block(themes)
    assert 'fg "#aabbcc"' in text
    assert 'bg "#112233"' in text
    # Sin raw_components, igual emite las 7 componentes ricas derivadas.
    assert "text_selected" in text
    assert "ribbon_selected" in text
    assert "frame_selected" in text


def test_render_drops_orange_legacy_slot() -> None:
    """orange ya no es legacy. Si llega un ZellijColor 'orange', no se
    emite en el bloque legacy del KDL."""
    theme = ZellijTheme(
        name="t",
        source="user",
        colors=[
            ZellijColor("fg", "#ffffff"),
            ZellijColor("orange", "#ff8800"),  # ignorado al renderizar
        ],
    )
    text = zellij_themes.render_themes_block([theme])
    # No aparece como nodo legacy 'orange'.
    assert "        orange " not in text


def test_render_emits_only_components_with_exposed_slots(tmp_path: Path) -> None:
    """Solo se emiten componentes que tienen al menos un slot expuesto.
    Por componente: 5 slots obligatorios para Zellij (base + emphasis_0..3)
    + `background` solo si esta expuesto. Override del usuario gana sobre
    derivacion."""
    legacy_dict = {"red": "#ff0000", "green": "#00ff00", "blue": "#0000ff"}
    legacy = [
        ZellijColor(name=s, value=legacy_dict.get(s, "#abcdef"))
        for s in zellij_themes.LEGACY_SLOTS
    ]
    theme = ZellijTheme(name="t", source="user", colors=legacy)
    zellij_themes.set_rich_slot(theme, "text_selected", "background", "#deadbe")
    text = zellij_themes.render_themes_block([theme])

    # Componentes con `background` expuesto -> emiten 6 slots.
    for component in ("text_unselected", "text_selected", "ribbon_unselected", "ribbon_selected"):
        assert f"{component} {{" in text, f"falta {component}"
        for slot in ("base", "background", "emphasis_0", "emphasis_1", "emphasis_2", "emphasis_3"):
            block_start = text.index(f"{component} {{")
            block_end = text.index("}", block_start)
            block = text[block_start:block_end]
            assert f"{slot} " in block, f"{component}.{slot} ausente"

    # frame_*: solo `base` expuesto -> emiten 5 slots (sin background).
    for component in ("frame_unselected", "frame_selected", "frame_highlight"):
        assert f"{component} {{" in text, f"falta {component}"
        block_start = text.index(f"{component} {{")
        block_end = text.index("}", block_start)
        block = text[block_start:block_end]
        for slot in ("base", "emphasis_0", "emphasis_1", "emphasis_2", "emphasis_3"):
            assert f"{slot} " in block, f"{component}.{slot} ausente"
        assert "background " not in block, f"{component}.background no debe emitirse"

    # exit_code_error sin slots expuestos -> no aparece en el .kdl.
    assert "exit_code_error" not in text

    # Override puntual presente.
    assert '"#deadbe"' in text
    # Slot derivado: ribbon_selected.background = palette.green.
    assert 'background "#00ff00"' in text


def test_derive_rich_block_matches_zellij_from_palette() -> None:
    """Smoke test del puerto Python de From<Palette> for Styling.
    Orange viene de orange_hint (text_unselected.emphasis_0 en el modelo
    rico); el palette legacy ya no lo incluye."""
    palette = {
        "fg": "#f0f0f0",
        "bg": "#101010",
        "black": "#000000",
        "red": "#ff0000",
        "green": "#00ff00",
        "yellow": "#ffff00",
        "blue": "#0000ff",
        "magenta": "#ff00ff",
        "cyan": "#00ffff",
        "white": "#ffffff",
    }
    derived = zellij_themes.derive_rich_block(palette, orange_hint="#ffa500")
    # Tabs activa: ribbon_selected.background = palette.green.
    assert derived["ribbon_selected"]["background"] == "#00ff00"
    assert derived["ribbon_selected"]["base"] == "#000000"
    # Tabs inactiva: ribbon_unselected.background = palette.fg.
    assert derived["ribbon_unselected"]["background"] == "#f0f0f0"
    # Frame highlight (active border): base = orange_hint.
    assert derived["frame_highlight"]["base"] == "#ffa500"
    # Frame selected: base = palette.green.
    assert derived["frame_selected"]["base"] == "#00ff00"
    # text_unselected.background = palette.black (theme_hue=Dark).
    assert derived["text_unselected"]["background"] == "#000000"


def test_default_legacy_slots() -> None:
    slots = zellij_themes.default_legacy_slots()
    assert [s.name for s in slots] == list(zellij_themes.LEGACY_SLOTS)
    assert all(s.value.startswith("#") for s in slots)
