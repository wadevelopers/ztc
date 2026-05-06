from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import tomlkit

from term_config_tui.services import colors
from term_config_tui.services.terminals.alacritty import (
    KNOWN_SLOTS,
    AlacrittyBackend,
)

FIX = Path(__file__).parent / "fixtures" / "alacritty"


def _slots_from_doc(
    backend: AlacrittyBackend, doc: tomlkit.TOMLDocument
) -> dict[tuple[str, str], str]:
    return {
        slot: v
        for slot in KNOWN_SLOTS
        for v in [backend.read_slot(doc, slot)]
        if v is not None
    }


def test_is_valid_hex() -> None:
    assert colors.is_valid_hex("#fff")
    assert colors.is_valid_hex("#ABCDEF")
    assert colors.is_valid_hex("#11223344")
    assert not colors.is_valid_hex("fff")
    assert not colors.is_valid_hex("#xyz")
    assert not colors.is_valid_hex("")
    assert not colors.is_valid_hex("#12345")


def test_normalize_hex_lowercases_and_adds_hash() -> None:
    assert colors.normalize_hex("#FF00AA") == "#ff00aa"
    assert colors.normalize_hex("ABCDEF") == "#abcdef"


def test_read_slot_returns_value(tmp_path: Path) -> None:
    src = tmp_path / "alacritty.toml"
    shutil.copy2(FIX / "alacritty_min.toml", src)
    backend = AlacrittyBackend()
    doc = backend.load(src)
    assert backend.read_slot(doc, ("primary", "background")) == "#1e1e2e"
    assert backend.read_slot(doc, ("normal", "blue")) is None  # no esta definido


def test_write_slot_creates_tables_when_missing() -> None:
    backend = AlacrittyBackend()
    doc = tomlkit.document()
    backend.write_slot(doc, ("primary", "background"), "#000000")
    assert doc["colors"]["primary"]["background"] == "#000000"


def test_delete_slot_removes_existing(tmp_path: Path) -> None:
    src = tmp_path / "a.toml"
    shutil.copy2(FIX / "alacritty_min.toml", src)
    backend = AlacrittyBackend()
    doc = backend.load(src)
    assert backend.read_slot(doc, ("primary", "background")) == "#1e1e2e"
    assert backend.delete_slot(doc, ("primary", "background")) is True
    assert backend.read_slot(doc, ("primary", "background")) is None
    # foreground sigue ahi.
    assert backend.read_slot(doc, ("primary", "foreground")) == "#cdd6f4"


def test_delete_slot_returns_false_if_missing() -> None:
    backend = AlacrittyBackend()
    doc = tomlkit.document()
    assert backend.delete_slot(doc, ("cursor", "text")) is False


def test_delete_slot_collapses_empty_group() -> None:
    """Al borrar el ultimo slot del grupo, la tabla del grupo se elimina."""
    backend = AlacrittyBackend()
    doc = tomlkit.document()
    backend.write_slot(doc, ("cursor", "text"), "#333333")
    backend.write_slot(doc, ("cursor", "cursor"), "#333333")
    backend.delete_slot(doc, ("cursor", "text"))
    assert "cursor" in doc["colors"]  # type: ignore[index]
    backend.delete_slot(doc, ("cursor", "cursor"))
    assert "cursor" not in doc.get("colors", {})


def test_write_slot_preserves_other_keys(tmp_path: Path) -> None:
    src = tmp_path / "a.toml"
    shutil.copy2(FIX / "alacritty_min.toml", src)
    backend = AlacrittyBackend()
    doc = backend.load(src)
    backend.write_slot(doc, ("primary", "background"), "#abcdef")
    assert doc["colors"]["primary"]["foreground"] == "#cdd6f4"
    assert doc["window"]["opacity"] == 0.97  # type: ignore[index]


def test_read_all_slots_only_returns_defined(tmp_path: Path) -> None:
    src = tmp_path / "a.toml"
    shutil.copy2(FIX / "alacritty_min.toml", src)
    backend = AlacrittyBackend()
    doc = backend.load(src)
    slots = backend.read_all_slots(doc)
    assert ("primary", "background") in slots
    assert ("normal", "red") in slots
    assert ("normal", "blue") not in slots  # ausente en el fixture min


def test_import_theme_overwrites_defined_slots(tmp_path: Path) -> None:
    src = tmp_path / "a.toml"
    shutil.copy2(FIX / "alacritty_min.toml", src)
    backend = AlacrittyBackend()
    doc = backend.load(src)
    count = backend.import_theme_file(doc, FIX / "dracula.toml")
    # Dracula define 2 (primary) + 8 (normal) + 2 (cursor) = 12 slots conocidos.
    assert count == 12
    assert backend.read_slot(doc, ("primary", "background")) == "#282a36"
    assert backend.read_slot(doc, ("normal", "red")) == "#ff5555"
    assert backend.read_slot(doc, ("cursor", "cursor")) == "#f8f8f2"


def test_import_theme_missing_file(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    doc = tomlkit.document()
    with pytest.raises(FileNotFoundError):
        backend.import_theme_file(doc, tmp_path / "nope.toml")


def test_add_import_creates_array_and_dedupes() -> None:
    backend = AlacrittyBackend()
    doc = tomlkit.document()
    assert backend.add_import(doc, "~/themes/dracula.toml") is True
    assert backend.add_import(doc, "~/themes/dracula.toml") is False
    assert backend.get_imports(doc) == ["~/themes/dracula.toml"]
    assert backend.add_import(doc, "~/themes/nord.toml") is True
    assert backend.get_imports(doc) == [
        "~/themes/dracula.toml",
        "~/themes/nord.toml",
    ]


def test_contrast_ratio_known_values() -> None:
    # blanco vs negro = 21
    assert round(colors.contrast_ratio("#ffffff", "#000000") or 0, 1) == 21.0
    # mismo color = 1
    assert round(colors.contrast_ratio("#abcdef", "#abcdef") or 0, 2) == 1.0


def test_contrast_ratio_invalid_returns_none() -> None:
    assert colors.contrast_ratio("nope", "#000") is None


def test_compute_warnings_flags_low_fg_bg_contrast() -> None:
    backend = AlacrittyBackend()
    doc = tomlkit.document()
    backend.write_slot(doc, ("primary", "background"), "#1e1e2e")
    backend.write_slot(doc, ("primary", "foreground"), "#222222")
    warns = colors.compute_warnings(_slots_from_doc(backend, doc))
    assert any("foreground" in w.message for w in warns)


def test_compute_warnings_flags_bg_close_to_black() -> None:
    backend = AlacrittyBackend()
    doc = tomlkit.document()
    backend.write_slot(doc, ("primary", "background"), "#101010")
    backend.write_slot(doc, ("primary", "foreground"), "#ffffff")
    backend.write_slot(doc, ("normal", "black"), "#0e0e0e")
    warns = colors.compute_warnings(_slots_from_doc(backend, doc))
    assert any("normal.black" in w.message for w in warns)


def test_compute_warnings_flags_zellij_bg_clash() -> None:
    backend = AlacrittyBackend()
    doc = tomlkit.document()
    backend.write_slot(doc, ("primary", "background"), "#1e1e2e")
    backend.write_slot(doc, ("primary", "foreground"), "#ffffff")
    warns = colors.compute_warnings(
        _slots_from_doc(backend, doc), zellij_bg="#1f1f30"
    )
    assert any("zellij" in w.message.lower() for w in warns)


def test_compute_warnings_clean_when_high_contrast() -> None:
    backend = AlacrittyBackend()
    doc = tomlkit.document()
    backend.write_slot(doc, ("primary", "background"), "#000000")
    backend.write_slot(doc, ("primary", "foreground"), "#ffffff")
    backend.write_slot(doc, ("normal", "black"), "#aaaaaa")
    backend.write_slot(doc, ("selection", "background"), "#888888")
    backend.write_slot(doc, ("cursor", "cursor"), "#ffaa00")
    assert colors.compute_warnings(_slots_from_doc(backend, doc)) == []
