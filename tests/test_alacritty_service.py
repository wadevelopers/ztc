from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import tomlkit

from term_config_tui.services import alacritty, toml_io

FIX = Path(__file__).parent / "fixtures" / "alacritty"


def test_is_valid_hex() -> None:
    assert alacritty.is_valid_hex("#fff")
    assert alacritty.is_valid_hex("#ABCDEF")
    assert alacritty.is_valid_hex("#11223344")
    assert not alacritty.is_valid_hex("fff")
    assert not alacritty.is_valid_hex("#xyz")
    assert not alacritty.is_valid_hex("")
    assert not alacritty.is_valid_hex("#12345")


def test_normalize_hex_lowercases_and_adds_hash() -> None:
    assert alacritty.normalize_hex("#FF00AA") == "#ff00aa"
    assert alacritty.normalize_hex("ABCDEF") == "#abcdef"


def test_read_slot_returns_value(tmp_path: Path) -> None:
    src = tmp_path / "alacritty.toml"
    shutil.copy2(FIX / "alacritty_min.toml", src)
    doc = toml_io.load_toml(src)
    assert alacritty.read_slot(doc, "primary", "background") == "#1e1e2e"
    assert alacritty.read_slot(doc, "normal", "blue") is None  # no esta definido


def test_write_slot_creates_tables_when_missing() -> None:
    doc = tomlkit.document()
    alacritty.write_slot(doc, "primary", "background", "#000000")
    assert doc["colors"]["primary"]["background"] == "#000000"


def test_delete_slot_removes_existing(tmp_path: Path) -> None:
    src = tmp_path / "a.toml"
    shutil.copy2(FIX / "alacritty_min.toml", src)
    doc = toml_io.load_toml(src)
    assert alacritty.read_slot(doc, "primary", "background") == "#1e1e2e"
    assert alacritty.delete_slot(doc, "primary", "background") is True
    assert alacritty.read_slot(doc, "primary", "background") is None
    # foreground sigue ahi.
    assert alacritty.read_slot(doc, "primary", "foreground") == "#cdd6f4"


def test_delete_slot_returns_false_if_missing() -> None:
    doc = tomlkit.document()
    assert alacritty.delete_slot(doc, "cursor", "text") is False


def test_delete_slot_collapses_empty_group(tmp_path: Path) -> None:
    """Al borrar el ultimo slot del grupo, la tabla del grupo se elimina."""
    doc = tomlkit.document()
    alacritty.write_slot(doc, "cursor", "text", "#333333")
    alacritty.write_slot(doc, "cursor", "cursor", "#333333")
    alacritty.delete_slot(doc, "cursor", "text")
    assert "cursor" in doc["colors"]  # type: ignore[index]
    alacritty.delete_slot(doc, "cursor", "cursor")
    assert "cursor" not in doc.get("colors", {})


def test_write_slot_preserves_other_keys(tmp_path: Path) -> None:
    src = tmp_path / "a.toml"
    shutil.copy2(FIX / "alacritty_min.toml", src)
    doc = toml_io.load_toml(src)
    alacritty.write_slot(doc, "primary", "background", "#abcdef")
    assert doc["colors"]["primary"]["foreground"] == "#cdd6f4"
    assert doc["window"]["opacity"] == 0.97  # type: ignore[index]


def test_read_all_slots_only_returns_defined(tmp_path: Path) -> None:
    src = tmp_path / "a.toml"
    shutil.copy2(FIX / "alacritty_min.toml", src)
    doc = toml_io.load_toml(src)
    slots = alacritty.read_all_slots(doc)
    assert ("primary", "background") in slots
    assert ("normal", "red") in slots
    assert ("normal", "blue") not in slots  # ausente en el fixture min


def test_import_theme_overwrites_defined_slots(tmp_path: Path) -> None:
    src = tmp_path / "a.toml"
    shutil.copy2(FIX / "alacritty_min.toml", src)
    doc = toml_io.load_toml(src)
    count = alacritty.import_theme_file(doc, FIX / "dracula.toml")
    # Dracula define 2 (primary) + 8 (normal) + 2 (cursor) = 12 slots conocidos.
    assert count == 12
    assert alacritty.read_slot(doc, "primary", "background") == "#282a36"
    assert alacritty.read_slot(doc, "normal", "red") == "#ff5555"
    assert alacritty.read_slot(doc, "cursor", "cursor") == "#f8f8f2"


def test_import_theme_missing_file(tmp_path: Path) -> None:
    doc = tomlkit.document()
    with pytest.raises(FileNotFoundError):
        alacritty.import_theme_file(doc, tmp_path / "nope.toml")


def test_add_import_creates_array_and_dedupes() -> None:
    doc = tomlkit.document()
    assert alacritty.add_import(doc, "~/themes/dracula.toml") is True
    assert alacritty.add_import(doc, "~/themes/dracula.toml") is False
    assert alacritty.get_imports(doc) == ["~/themes/dracula.toml"]
    assert alacritty.add_import(doc, "~/themes/nord.toml") is True
    assert alacritty.get_imports(doc) == [
        "~/themes/dracula.toml",
        "~/themes/nord.toml",
    ]


def test_contrast_ratio_known_values() -> None:
    # blanco vs negro = 21
    assert round(alacritty.contrast_ratio("#ffffff", "#000000") or 0, 1) == 21.0
    # mismo color = 1
    assert round(alacritty.contrast_ratio("#abcdef", "#abcdef") or 0, 2) == 1.0


def test_contrast_ratio_invalid_returns_none() -> None:
    assert alacritty.contrast_ratio("nope", "#000") is None


def test_compute_warnings_flags_low_fg_bg_contrast() -> None:
    doc = tomlkit.document()
    alacritty.write_slot(doc, "primary", "background", "#1e1e2e")
    alacritty.write_slot(doc, "primary", "foreground", "#222222")
    warns = alacritty.compute_warnings(doc)
    assert any("foreground" in w.message for w in warns)


def test_compute_warnings_flags_bg_close_to_black() -> None:
    doc = tomlkit.document()
    alacritty.write_slot(doc, "primary", "background", "#101010")
    alacritty.write_slot(doc, "primary", "foreground", "#ffffff")
    alacritty.write_slot(doc, "normal", "black", "#0e0e0e")
    warns = alacritty.compute_warnings(doc)
    assert any("normal.black" in w.message for w in warns)


def test_compute_warnings_flags_zellij_bg_clash() -> None:
    doc = tomlkit.document()
    alacritty.write_slot(doc, "primary", "background", "#1e1e2e")
    alacritty.write_slot(doc, "primary", "foreground", "#ffffff")
    warns = alacritty.compute_warnings(doc, zellij_bg="#1f1f30")
    assert any("zellij" in w.message.lower() for w in warns)


def test_compute_warnings_clean_when_high_contrast() -> None:
    doc = tomlkit.document()
    alacritty.write_slot(doc, "primary", "background", "#000000")
    alacritty.write_slot(doc, "primary", "foreground", "#ffffff")
    alacritty.write_slot(doc, "normal", "black", "#aaaaaa")
    alacritty.write_slot(doc, "selection", "background", "#888888")
    alacritty.write_slot(doc, "cursor", "cursor", "#ffaa00")
    assert alacritty.compute_warnings(doc) == []
