from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ztc.services.terminals.kitty import (
    KittyBackend,
    is_listen_on_set,
    is_remote_control_disabled,
    read_listen_on,
    read_remote_control,
    read_ztc_pref,
    write_listen_on_default,
    write_remote_control_yes,
    write_ztc_pref,
)

FIX = Path(__file__).parent / "fixtures" / "kitty"


def _copy_fixture(tmp_path: Path) -> Path:
    dst = tmp_path / "kitty.conf"
    shutil.copy2(FIX / "kitty.conf", dst)
    return dst


# ---------- mapping basico ----------


def test_supported_slots_has_20_slots() -> None:
    backend = KittyBackend()
    slots = backend.supported_slots()
    # primary 2 + normal 8 + bright 8 + selection 2 + cursor 2 = 22.
    # (Kitty cubre los mismos 22; matches Alacritty.)
    assert len(slots) == 22
    assert ("primary", "background") in slots
    assert ("bright", "white") in slots
    assert ("cursor", "text") in slots


def test_read_slot_basic_values(tmp_path: Path) -> None:
    p = _copy_fixture(tmp_path)
    backend = KittyBackend()
    doc = backend.load(p)
    assert backend.read_slot(doc, ("primary", "background")) == "#1e1e2e"
    assert backend.read_slot(doc, ("primary", "foreground")) == "#cdd6f4"
    assert backend.read_slot(doc, ("normal", "red")) == "#f38ba8"
    assert backend.read_slot(doc, ("bright", "white")) == "#a6adc8"
    assert backend.read_slot(doc, ("selection", "background")) == "#f5e0dc"
    assert backend.read_slot(doc, ("cursor", "cursor")) == "#f5e0dc"
    assert backend.read_slot(doc, ("cursor", "text")) == "#1e1e2e"


def test_read_slot_returns_none_for_undefined(tmp_path: Path) -> None:
    backend = KittyBackend()
    doc = backend.load(tmp_path / "missing.conf")  # archivo inexistente
    assert backend.read_slot(doc, ("primary", "background")) is None


# ---------- write/delete ----------


def test_write_slot_updates_existing_line(tmp_path: Path) -> None:
    p = _copy_fixture(tmp_path)
    backend = KittyBackend()
    doc = backend.load(p)
    backend.write_slot(doc, ("primary", "background"), "#000000")
    assert backend.read_slot(doc, ("primary", "background")) == "#000000"


def test_write_slot_appends_when_missing(tmp_path: Path) -> None:
    """Slot ausente del archivo -> append al final."""
    p = tmp_path / "kitty.conf"
    p.write_text("foreground #ffffff\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(p)
    assert backend.read_slot(doc, ("cursor", "cursor")) is None
    backend.write_slot(doc, ("cursor", "cursor"), "#abcdef")
    assert backend.read_slot(doc, ("cursor", "cursor")) == "#abcdef"
    # Y la nueva linea esta al final.
    assert doc.lines[-1] == "cursor #abcdef"


def test_delete_slot_removes_line(tmp_path: Path) -> None:
    p = _copy_fixture(tmp_path)
    backend = KittyBackend()
    doc = backend.load(p)
    assert backend.delete_slot(doc, ("cursor", "cursor")) is True
    assert backend.read_slot(doc, ("cursor", "cursor")) is None


def test_delete_slot_returns_false_if_missing(tmp_path: Path) -> None:
    backend = KittyBackend()
    doc = backend.load(tmp_path / "missing.conf")
    assert backend.delete_slot(doc, ("cursor", "cursor")) is False


# ---------- duplicados (last-occurrence-wins) ----------


def test_duplicate_keys_last_wins_on_read(tmp_path: Path) -> None:
    p = tmp_path / "k.conf"
    p.write_text(
        "color0 #111111\n"
        "color0 #222222\n"
        "color0 #333333\n",
        encoding="utf-8",
    )
    backend = KittyBackend()
    doc = backend.load(p)
    assert backend.read_slot(doc, ("normal", "black")) == "#333333"


def test_duplicate_keys_write_updates_last(tmp_path: Path) -> None:
    p = tmp_path / "k.conf"
    p.write_text(
        "color0 #111111\n"
        "color0 #222222\n"
        "color0 #333333\n",
        encoding="utf-8",
    )
    backend = KittyBackend()
    doc = backend.load(p)
    backend.write_slot(doc, ("normal", "black"), "#abcdef")
    # Solo la ultima cambia; las dos primeras quedan.
    assert doc.lines == [
        "color0 #111111",
        "color0 #222222",
        "color0 #abcdef",
    ]


# ---------- hex shorthand y normalizacion ----------


def test_hex_shorthand_expanded_on_read(tmp_path: Path) -> None:
    p = tmp_path / "k.conf"
    p.write_text("color1 #f00\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(p)
    assert backend.read_slot(doc, ("normal", "red")) == "#ff0000"


def test_hex_uppercase_normalized_to_lowercase(tmp_path: Path) -> None:
    p = tmp_path / "k.conf"
    p.write_text("color1 #FF00AA\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(p)
    assert backend.read_slot(doc, ("normal", "red")) == "#ff00aa"


# ---------- valores especiales / no-hex ----------


def test_special_value_none_preserved(tmp_path: Path) -> None:
    p = tmp_path / "k.conf"
    p.write_text("selection_foreground none\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(p)
    assert backend.read_slot(doc, ("selection", "text")) == "none"


def test_special_value_background_for_cursor(tmp_path: Path) -> None:
    p = tmp_path / "k.conf"
    p.write_text("cursor background\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(p)
    assert backend.read_slot(doc, ("cursor", "cursor")) == "background"


def test_special_value_named_color_preserved(tmp_path: Path) -> None:
    p = tmp_path / "k.conf"
    p.write_text("color1 red\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(p)
    assert backend.read_slot(doc, ("normal", "red")) == "red"


def test_special_value_oklch_preserved(tmp_path: Path) -> None:
    p = tmp_path / "k.conf"
    p.write_text("color1 oklch(0.7 0.25 25)\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(p)
    assert backend.read_slot(doc, ("normal", "red")) == "oklch(0.7 0.25 25)"


# ---------- includes ----------


def test_include_directive_preserved_in_doc(tmp_path: Path) -> None:
    """`include` queda en doc.lines pero no se expande."""
    p = _copy_fixture(tmp_path)
    backend = KittyBackend()
    doc = backend.load(p)
    assert any(line.startswith("include ") for line in doc.lines)


def test_writing_new_slot_after_include_appends(tmp_path: Path) -> None:
    p = tmp_path / "k.conf"
    p.write_text(
        "include other.conf\n"
        "foreground #ffffff\n",
        encoding="utf-8",
    )
    backend = KittyBackend()
    doc = backend.load(p)
    backend.write_slot(doc, ("normal", "red"), "#ff0000")
    # La nueva linea queda al final, despues del foreground.
    assert doc.lines[-1] == "color1 #ff0000"


# ---------- expansion de includes (lectura) ----------


def test_include_expanded_for_reads(tmp_path: Path) -> None:
    """Un slot definido solo en un include se ve via read_slot."""
    theme = tmp_path / "theme.conf"
    theme.write_text(
        "background #1a1b26\nforeground #c0caf5\ncolor1 #f7768e\n",
        encoding="utf-8",
    )
    main = tmp_path / "kitty.conf"
    main.write_text("include theme.conf\nfont_size 12.0\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(main)
    assert backend.read_slot(doc, ("primary", "background")) == "#1a1b26"
    assert backend.read_slot(doc, ("primary", "foreground")) == "#c0caf5"
    assert backend.read_slot(doc, ("normal", "red")) == "#f7768e"


def test_include_relative_path(tmp_path: Path) -> None:
    """Path relativo se resuelve contra el archivo padre, no el CWD."""
    sub = tmp_path / "themes"
    sub.mkdir()
    (sub / "tokyo.conf").write_text("color1 #f7768e\n", encoding="utf-8")
    main = tmp_path / "kitty.conf"
    main.write_text("include themes/tokyo.conf\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(main)
    assert backend.read_slot(doc, ("normal", "red")) == "#f7768e"


def test_include_absolute_path(tmp_path: Path) -> None:
    theme = tmp_path / "absolute_theme.conf"
    theme.write_text("color2 #00ff00\n", encoding="utf-8")
    main = tmp_path / "kitty.conf"
    main.write_text(f"include {theme}\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(main)
    assert backend.read_slot(doc, ("normal", "green")) == "#00ff00"


def test_include_missing_file_silently_ignored(tmp_path: Path) -> None:
    main = tmp_path / "kitty.conf"
    main.write_text("include nonexistent.conf\ncolor1 #ff0000\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(main)
    # No crashea; lo que esta en main funciona normal.
    assert backend.read_slot(doc, ("normal", "red")) == "#ff0000"


def test_main_overrides_include_when_after(tmp_path: Path) -> None:
    """Si main tiene la key DESPUES del include, gana main."""
    theme = tmp_path / "theme.conf"
    theme.write_text("color1 #aaaaaa\n", encoding="utf-8")
    main = tmp_path / "kitty.conf"
    main.write_text(
        "include theme.conf\ncolor1 #bbbbbb\n", encoding="utf-8"
    )
    backend = KittyBackend()
    doc = backend.load(main)
    assert backend.read_slot(doc, ("normal", "red")) == "#bbbbbb"


def test_include_overrides_main_when_after(tmp_path: Path) -> None:
    """Si main tiene la key ANTES del include, gana el include."""
    theme = tmp_path / "theme.conf"
    theme.write_text("color1 #aaaaaa\n", encoding="utf-8")
    main = tmp_path / "kitty.conf"
    main.write_text(
        "color1 #bbbbbb\ninclude theme.conf\n", encoding="utf-8"
    )
    backend = KittyBackend()
    doc = backend.load(main)
    assert backend.read_slot(doc, ("normal", "red")) == "#aaaaaa"


def test_nested_include(tmp_path: Path) -> None:
    """include de un archivo que tiene su propio include."""
    inner = tmp_path / "inner.conf"
    inner.write_text("color1 #112233\n", encoding="utf-8")
    middle = tmp_path / "middle.conf"
    middle.write_text("include inner.conf\n", encoding="utf-8")
    main = tmp_path / "kitty.conf"
    main.write_text("include middle.conf\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(main)
    assert backend.read_slot(doc, ("normal", "red")) == "#112233"


def test_circular_include_does_not_loop(tmp_path: Path) -> None:
    """Un include circular hits depth limit en lugar de loopear."""
    a = tmp_path / "a.conf"
    b = tmp_path / "b.conf"
    a.write_text("color1 #a1a1a1\ninclude b.conf\n", encoding="utf-8")
    b.write_text("color2 #b2b2b2\ninclude a.conf\n", encoding="utf-8")
    main = tmp_path / "kitty.conf"
    main.write_text("include a.conf\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(main)
    # No infinite loop: el read termina y devuelve algo razonable.
    assert backend.read_slot(doc, ("normal", "red")) == "#a1a1a1"
    assert backend.read_slot(doc, ("normal", "green")) == "#b2b2b2"


# ---------- escritura con includes ----------


def test_write_slot_only_in_include_appends_to_main(tmp_path: Path) -> None:
    """Si el slot solo esta en el include, write_slot appendea al main
    (gana via last-wins de kitty)."""
    theme = tmp_path / "theme.conf"
    theme.write_text("color1 #aaaaaa\n", encoding="utf-8")
    main = tmp_path / "kitty.conf"
    main.write_text("include theme.conf\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(main)
    backend.write_slot(doc, ("normal", "red"), "#ff0000")
    # No tocamos el include.
    assert "color1 #aaaaaa" in theme.read_text(encoding="utf-8")
    # Append al main.
    assert doc.lines[-1] == "color1 #ff0000"
    # Y el effective ahora es el del main.
    assert backend.read_slot(doc, ("normal", "red")) == "#ff0000"


def test_write_slot_already_in_main_updates_in_place(tmp_path: Path) -> None:
    """Si la entrada ganadora viene del main, update in-place (no append)."""
    theme = tmp_path / "theme.conf"
    theme.write_text("color1 #aaaaaa\n", encoding="utf-8")
    main = tmp_path / "kitty.conf"
    main.write_text(
        "include theme.conf\ncolor1 #bbbbbb\nfont_size 12.0\n",
        encoding="utf-8",
    )
    backend = KittyBackend()
    doc = backend.load(main)
    backend.write_slot(doc, ("normal", "red"), "#ff0000")
    # La linea de main fue actualizada in-place; no se agrego nada al final.
    assert doc.lines == [
        "include theme.conf",
        "color1 #ff0000",
        "font_size 12.0",
    ]


def test_write_slot_when_include_after_main_appends(tmp_path: Path) -> None:
    """Main tiene color1 ANTES del include (que tambien tiene color1).
    El effective viene del include. write_slot debe appendear, no
    actualizar la linea del main (porque el include la sobrescribiria)."""
    theme = tmp_path / "theme.conf"
    theme.write_text("color1 #aaaaaa\n", encoding="utf-8")
    main = tmp_path / "kitty.conf"
    main.write_text(
        "color1 #bbbbbb\ninclude theme.conf\n", encoding="utf-8"
    )
    backend = KittyBackend()
    doc = backend.load(main)
    backend.write_slot(doc, ("normal", "red"), "#ff0000")
    # La linea original de main no se toco.
    assert doc.lines[0] == "color1 #bbbbbb"
    # Append al final.
    assert doc.lines[-1] == "color1 #ff0000"
    # Effective: el append.
    assert backend.read_slot(doc, ("normal", "red")) == "#ff0000"


def test_delete_slot_only_removes_from_main(tmp_path: Path) -> None:
    """Borrar un slot que esta en main Y en include: solo se borra del
    main; el del include vuelve a ser efectivo."""
    theme = tmp_path / "theme.conf"
    theme.write_text("color1 #aaaaaa\n", encoding="utf-8")
    main = tmp_path / "kitty.conf"
    main.write_text(
        "include theme.conf\ncolor1 #bbbbbb\n", encoding="utf-8"
    )
    backend = KittyBackend()
    doc = backend.load(main)
    assert backend.read_slot(doc, ("normal", "red")) == "#bbbbbb"
    assert backend.delete_slot(doc, ("normal", "red")) is True
    # Despues del delete, gana el del include.
    assert backend.read_slot(doc, ("normal", "red")) == "#aaaaaa"
    # El theme.conf no se tocó.
    assert "color1 #aaaaaa" in theme.read_text(encoding="utf-8")


def test_delete_slot_only_in_include_returns_false(tmp_path: Path) -> None:
    """Si el slot esta solo en el include, delete devuelve False
    (no tocamos includes)."""
    theme = tmp_path / "theme.conf"
    theme.write_text("color1 #aaaaaa\n", encoding="utf-8")
    main = tmp_path / "kitty.conf"
    main.write_text("include theme.conf\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(main)
    assert backend.delete_slot(doc, ("normal", "red")) is False
    # El effective sigue siendo el del include.
    assert backend.read_slot(doc, ("normal", "red")) == "#aaaaaa"


# ---------- comentarios y formato ----------


def test_comments_preserved_in_doc(tmp_path: Path) -> None:
    p = _copy_fixture(tmp_path)
    backend = KittyBackend()
    doc = backend.load(p)
    assert any(line.startswith("# ") for line in doc.lines)


def test_indented_lines_are_parsed(tmp_path: Path) -> None:
    """Indentacion al inicio no impide parsear la key."""
    p = tmp_path / "k.conf"
    p.write_text("    color1 #ff0000\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(p)
    assert backend.read_slot(doc, ("normal", "red")) == "#ff0000"


def test_blank_lines_preserved(tmp_path: Path) -> None:
    p = tmp_path / "k.conf"
    p.write_text("foreground #fff\n\ncolor0 #000\n", encoding="utf-8")
    backend = KittyBackend()
    doc = backend.load(p)
    # Hay al menos una linea blanca entre las dos.
    assert "" in doc.lines


# ---------- roundtrip ----------


def test_roundtrip_preserves_unchanged_lines(tmp_path: Path) -> None:
    p = _copy_fixture(tmp_path)
    backend = KittyBackend()
    doc = backend.load(p)
    # Sin modificaciones, save deberia producir el mismo contenido (modulo
    # normalizacion de un trailing newline).
    backend.save(doc, p)
    expected = (FIX / "kitty.conf").read_text(encoding="utf-8")
    actual = p.read_text(encoding="utf-8")
    assert actual == expected


def test_roundtrip_preserves_non_color_lines_after_edit(tmp_path: Path) -> None:
    p = _copy_fixture(tmp_path)
    backend = KittyBackend()
    doc = backend.load(p)
    backend.write_slot(doc, ("primary", "background"), "#abcdef")
    backend.save(doc, p)
    text = p.read_text(encoding="utf-8")
    # Cambio aplicado.
    assert "background #abcdef" in text
    # No-colors preservados.
    assert "font_family JetBrains Mono" in text
    assert "font_size 12.0" in text
    assert "include themes/base.conf" in text
    assert "enable_audio_bell no" in text
    # Comentario preservado.
    assert "# Kitty config de ejemplo para tests." in text


# ---------- save / backup ----------


def test_save_creates_backup_when_file_existed(tmp_path: Path) -> None:
    p = _copy_fixture(tmp_path)
    backend = KittyBackend()
    doc = backend.load(p)
    backup = backend.save(doc, p)
    assert backup is not None
    assert backup.exists()


def test_save_returns_none_when_no_previous_file(tmp_path: Path) -> None:
    """Si el archivo no existia, no hay backup que crear."""
    p = tmp_path / "new.conf"
    backend = KittyBackend()
    doc = backend.load(p)  # devuelve doc vacio
    backend.write_slot(doc, ("primary", "background"), "#000000")
    backup = backend.save(doc, p)
    assert backup is None
    assert p.exists()
    assert p.read_text(encoding="utf-8").rstrip() == "background #000000"


# ---------- default_config_path ----------


def test_default_config_path_kitty_config_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KITTY_CONFIG_DIRECTORY", "/custom/kitty")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    backend = KittyBackend()
    assert backend.default_config_path() == Path("/custom/kitty/kitty.conf")


def test_default_config_path_xdg_config_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KITTY_CONFIG_DIRECTORY", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", "/myhome/.cfg")
    backend = KittyBackend()
    assert backend.default_config_path() == Path("/myhome/.cfg/kitty/kitty.conf")


def test_default_config_path_fallback_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KITTY_CONFIG_DIRECTORY", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    backend = KittyBackend()
    assert backend.default_config_path() == Path.home() / ".config" / "kitty" / "kitty.conf"


# ---------- integracion con registry ----------


def test_registry_resolves_kitty_backend() -> None:
    from ztc.services.terminals.registry import (
        get_backend,
        is_backend_available,
    )

    assert is_backend_available("kitty") is True
    assert "kitty" in __import__(
        "ztc.services.terminals.registry", fromlist=["available_kinds"]
    ).available_kinds()
    backend = get_backend("kitty")
    assert isinstance(backend, KittyBackend)


# ---------- import_theme_file ----------


def test_import_theme_file_copies_color_slots(tmp_path: Path) -> None:
    """Crea un .conf source con colores distintos a los del fixture y
    los mergea sobre el doc destino. Los slots quedan con los valores
    del source."""
    backend = KittyBackend()
    dst = _copy_fixture(tmp_path)
    doc = backend.load(dst)

    source = tmp_path / "theme.conf"
    source.write_text(
        "background #112233\n"
        "foreground #aabbcc\n"
        "color1 #ff0000\n",
        encoding="utf-8",
    )

    count = backend.import_theme_file(doc, source)

    assert count == 3
    assert backend.read_slot(doc, ("primary", "background")) == "#112233"
    assert backend.read_slot(doc, ("primary", "foreground")) == "#aabbcc"
    assert backend.read_slot(doc, ("normal", "red")) == "#ff0000"


def test_import_theme_file_skips_invalid_hex(tmp_path: Path) -> None:
    """Source con valores invalidos (texto basura, hex incompleto):
    esos slots se ignoran, los validos se aplican."""
    backend = KittyBackend()
    dst = _copy_fixture(tmp_path)
    doc = backend.load(dst)

    bg_before = backend.read_slot(doc, ("primary", "background"))

    source = tmp_path / "theme.conf"
    source.write_text(
        "background not-a-color\n"
        "foreground #abcabc\n"
        "color1 #zzz\n",
        encoding="utf-8",
    )

    count = backend.import_theme_file(doc, source)

    assert count == 1
    # Solo foreground se importa.
    assert backend.read_slot(doc, ("primary", "foreground")) == "#abcabc"
    # background se preserva (no fue sobreescrito por valor invalido).
    assert backend.read_slot(doc, ("primary", "background")) == bg_before


def test_import_theme_file_raises_on_missing_source(tmp_path: Path) -> None:
    """Source que no existe: FileNotFoundError. Espejo de Alacritty."""
    backend = KittyBackend()
    dst = _copy_fixture(tmp_path)
    doc = backend.load(dst)

    missing = tmp_path / "nonexistent.conf"
    with pytest.raises(FileNotFoundError):
        backend.import_theme_file(doc, missing)


def test_import_theme_file_returns_zero_when_no_color_slots(tmp_path: Path) -> None:
    """Source sin entradas reconocibles: count = 0, doc intacto."""
    backend = KittyBackend()
    dst = _copy_fixture(tmp_path)
    doc = backend.load(dst)
    fg_before = backend.read_slot(doc, ("primary", "foreground"))

    source = tmp_path / "theme.conf"
    source.write_text("# nothing useful\nfont_family Arial\n", encoding="utf-8")

    count = backend.import_theme_file(doc, source)

    assert count == 0
    assert backend.read_slot(doc, ("primary", "foreground")) == fg_before


# ---------- remote control / listen_on helpers ----------


def test_read_remote_control_values(tmp_path: Path) -> None:
    backend = KittyBackend()
    for value in ("yes", "no", "password", "socket", "socket-only"):
        path = tmp_path / f"{value}.conf"
        path.write_text(f"allow_remote_control {value}\n", encoding="utf-8")
        assert read_remote_control(backend.load(path)) == value
    assert read_remote_control(backend.load(tmp_path / "absent.conf")) is None


def test_read_remote_control_from_include(tmp_path: Path) -> None:
    inc = tmp_path / "remote.conf"
    inc.write_text("allow_remote_control socket-only\n", encoding="utf-8")
    main = tmp_path / "kitty.conf"
    main.write_text("include remote.conf\n", encoding="utf-8")
    assert read_remote_control(KittyBackend().load(main)) == "socket-only"


def test_is_remote_control_disabled_truth_table() -> None:
    assert is_remote_control_disabled(None) is True
    assert is_remote_control_disabled("no") is True
    for value in ("yes", "password", "socket", "socket-only", "None"):
        assert is_remote_control_disabled(value) is False


def test_write_remote_control_yes_appends(tmp_path: Path) -> None:
    doc = KittyBackend().load(tmp_path / "kitty.conf")
    write_remote_control_yes(doc)
    assert doc.lines[-1] == "allow_remote_control yes"


def test_read_listen_on_values_and_include(tmp_path: Path) -> None:
    inc = tmp_path / "listen.conf"
    inc.write_text("listen_on unix:@from-include\n", encoding="utf-8")
    main = tmp_path / "kitty.conf"
    main.write_text(
        "listen_on none\ninclude listen.conf\n", encoding="utf-8"
    )
    assert read_listen_on(KittyBackend().load(main)) == "unix:@from-include"


def test_read_listen_on_absent_and_none_literal(tmp_path: Path) -> None:
    backend = KittyBackend()
    absent = tmp_path / "absent.conf"
    assert read_listen_on(backend.load(absent)) is None
    none_path = tmp_path / "none.conf"
    none_path.write_text("listen_on none\n", encoding="utf-8")
    assert read_listen_on(backend.load(none_path)) == "none"


def test_is_listen_on_set_truth_table() -> None:
    assert is_listen_on_set(None) is False
    assert is_listen_on_set("") is False
    assert is_listen_on_set("   ") is False
    assert is_listen_on_set("none") is False
    assert is_listen_on_set("None") is True
    assert is_listen_on_set("unix:@ztc-1234") is True
    assert is_listen_on_set("unix:/tmp/sock") is True


def test_write_listen_on_default_appends(tmp_path: Path) -> None:
    doc = KittyBackend().load(tmp_path / "kitty.conf")
    write_listen_on_default(doc)
    assert doc.lines[-1] == "listen_on unix:@ztc-{kitty_pid}"


# ---------- # ztc prefs ----------


def test_ztc_pref_roundtrip_and_missing(tmp_path: Path) -> None:
    doc = KittyBackend().load(tmp_path / "kitty.conf")
    assert read_ztc_pref(doc, "remote_control_modal") is None
    write_ztc_pref(doc, "remote_control_modal", "dismissed")
    assert read_ztc_pref(doc, "remote_control_modal") == "dismissed"


def test_read_ztc_pref_ignores_malformed_and_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "kitty.conf"
    path.write_text(
        "# ztc:{bad\n"
        "# ztc:[1, 2]\n"
        "# ztc:42\n"
        '# ztc:{"ok": true}\n',
        encoding="utf-8",
    )
    assert read_ztc_pref(KittyBackend().load(path), "ok") is True


def test_multiple_ztc_lines_merge_last_wins_and_write_collapses(tmp_path: Path) -> None:
    path = tmp_path / "kitty.conf"
    path.write_text(
        "font_size 12.0\n"
        '# ztc:{"a": 1, "b": 1}\n'
        "foreground #ffffff\n"
        '# ztc:{"b": 2}\n',
        encoding="utf-8",
    )
    doc = KittyBackend().load(path)
    assert read_ztc_pref(doc, "a") == 1
    assert read_ztc_pref(doc, "b") == 2
    write_ztc_pref(doc, "c", 3)
    assert doc.lines == [
        "font_size 12.0",
        "foreground #ffffff",
        '# ztc:{"a": 1, "b": 2, "c": 3}',
    ]


# ---------- reload_after_save ----------


def test_reload_after_save_uses_env_target(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setenv("KITTY_LISTEN_ON", "unix:@ztc-1")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert KittyBackend().reload_after_save() is True
    assert calls == [["kitty", "@", "--to", "unix:@ztc-1", "load-config"]]


def test_reload_after_save_falls_back_to_kitten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1 if cmd[0] == "kitty" else 0)

    monkeypatch.delenv("KITTY_LISTEN_ON", raising=False)
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert KittyBackend().reload_after_save() is True
    assert calls == [["kitty", "@", "load-config"], ["kitten", "@", "load-config"]]


def test_reload_after_save_returns_false_on_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert KittyBackend().reload_after_save() is False


def test_reload_after_save_catches_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd, timeout=2)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert KittyBackend().reload_after_save() is False


def test_reload_after_save_catches_file_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert KittyBackend().reload_after_save() is False
