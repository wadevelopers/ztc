from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from term_config_tui.services.terminals.kitty import (
    KNOWN_SLOTS,
    KittyBackend,
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
    from term_config_tui.services.terminals.registry import (
        get_backend,
        is_backend_available,
    )

    assert is_backend_available("kitty") is True
    assert "kitty" in __import__(
        "term_config_tui.services.terminals.registry", fromlist=["available_kinds"]
    ).available_kinds()
    backend = get_backend("kitty")
    assert isinstance(backend, KittyBackend)
