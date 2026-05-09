"""Tests del backend Alacritty para settings (padding, opacity, font,
cursor shape). Cubre roundtrip read→write→read, delete, valores
invalidos (coercion devuelve None / write levanta ValueError), y
TOML inline tables vs dotted tables (deben ser equivalentes al leer)."""

from __future__ import annotations

import pytest
import tomlkit

from ztc.services.terminals.alacritty import AlacrittyBackend
from ztc.services.terminals.settings import SETTINGS


@pytest.fixture
def backend() -> AlacrittyBackend:
    return AlacrittyBackend()


def _doc_from(text: str):
    return tomlkit.parse(text)


# ---------- read: dotted tables ----------


def test_read_padding_from_dotted_table(backend: AlacrittyBackend) -> None:
    doc = _doc_from('[window.padding]\nx = 8\ny = 12\n')
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) == 8
    assert backend.read_setting(doc, SETTINGS["window.padding.y"]) == 12


def test_read_opacity_from_window_table(backend: AlacrittyBackend) -> None:
    doc = _doc_from('[window]\nopacity = 0.85\n')
    assert backend.read_setting(doc, SETTINGS["window.opacity"]) == 0.85


def test_read_font_size_and_family(backend: AlacrittyBackend) -> None:
    doc = _doc_from(
        '[font]\nsize = 14.0\n[font.normal]\nfamily = "JetBrains Mono"\n'
    )
    assert backend.read_setting(doc, SETTINGS["font.size"]) == 14.0
    assert (
        backend.read_setting(doc, SETTINGS["font.family"]) == "JetBrains Mono"
    )


def test_read_cursor_shape(backend: AlacrittyBackend) -> None:
    doc = _doc_from('[cursor.style]\nshape = "Beam"\n')
    assert backend.read_setting(doc, SETTINGS["cursor.shape"]) == "Beam"


# ---------- read: inline tables ----------


def test_read_padding_from_inline_table(backend: AlacrittyBackend) -> None:
    """`window = { padding = { x = 8, y = 12 } }` debe leerse igual que
    la forma dotted."""
    doc = _doc_from('window = { padding = { x = 8, y = 12 } }\n')
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) == 8
    assert backend.read_setting(doc, SETTINGS["window.padding.y"]) == 12


def test_read_cursor_shape_from_inline_table(backend: AlacrittyBackend) -> None:
    doc = _doc_from('cursor = { style = { shape = "Underline" } }\n')
    assert backend.read_setting(doc, SETTINGS["cursor.shape"]) == "Underline"


# ---------- read: missing entries ----------


def test_read_missing_setting_returns_none(backend: AlacrittyBackend) -> None:
    doc = _doc_from("# empty\n")
    for name in (
        "window.padding.x",
        "window.opacity",
        "font.size",
        "font.family",
        "cursor.shape",
    ):
        assert backend.read_setting(doc, SETTINGS[name]) is None


# ---------- write: roundtrip ----------


def test_write_then_read_padding(backend: AlacrittyBackend) -> None:
    doc = tomlkit.document()
    backend.write_setting(doc, SETTINGS["window.padding.x"], 10)
    backend.write_setting(doc, SETTINGS["window.padding.y"], 20)
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) == 10
    assert backend.read_setting(doc, SETTINGS["window.padding.y"]) == 20


def test_write_then_read_opacity(backend: AlacrittyBackend) -> None:
    doc = tomlkit.document()
    backend.write_setting(doc, SETTINGS["window.opacity"], 0.9)
    assert backend.read_setting(doc, SETTINGS["window.opacity"]) == 0.9


def test_write_then_read_font_family(backend: AlacrittyBackend) -> None:
    doc = tomlkit.document()
    backend.write_setting(doc, SETTINGS["font.family"], "Fira Code")
    assert backend.read_setting(doc, SETTINGS["font.family"]) == "Fira Code"


def test_write_then_read_cursor_shape(backend: AlacrittyBackend) -> None:
    doc = tomlkit.document()
    backend.write_setting(doc, SETTINGS["cursor.shape"], "Block")
    assert backend.read_setting(doc, SETTINGS["cursor.shape"]) == "Block"


# ---------- write: invalid values raise ValueError ----------


def test_write_invalid_int_raises(backend: AlacrittyBackend) -> None:
    doc = tomlkit.document()
    with pytest.raises(ValueError):
        backend.write_setting(doc, SETTINGS["window.padding.x"], -1)
    with pytest.raises(ValueError):
        backend.write_setting(doc, SETTINGS["window.padding.x"], "not-int")


def test_write_invalid_opacity_raises(backend: AlacrittyBackend) -> None:
    doc = tomlkit.document()
    with pytest.raises(ValueError):
        backend.write_setting(doc, SETTINGS["window.opacity"], 1.5)
    with pytest.raises(ValueError):
        backend.write_setting(doc, SETTINGS["window.opacity"], -0.1)


def test_write_invalid_enum_raises(backend: AlacrittyBackend) -> None:
    doc = tomlkit.document()
    with pytest.raises(ValueError):
        backend.write_setting(doc, SETTINGS["cursor.shape"], "Diamond")


def test_write_empty_str_raises(backend: AlacrittyBackend) -> None:
    doc = tomlkit.document()
    with pytest.raises(ValueError):
        backend.write_setting(doc, SETTINGS["font.family"], "")


# ---------- coerce: malformed values in file return None ----------


def test_read_malformed_int_returns_none(backend: AlacrittyBackend) -> None:
    doc = _doc_from('[window.padding]\nx = "not-a-number"\n')
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) is None


def test_read_float_for_int_setting_returns_none(
    backend: AlacrittyBackend,
) -> None:
    """Si Alacritty tiene `padding.x = 2.5` (no permitido pero valido
    TOML), el coerce devuelve None — no se intenta truncar."""
    doc = _doc_from('[window.padding]\nx = 2.5\n')
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) is None


# ---------- delete ----------


def test_delete_setting_removes_entry(backend: AlacrittyBackend) -> None:
    doc = _doc_from('[window]\nopacity = 0.8\n')
    assert backend.delete_setting(doc, SETTINGS["window.opacity"]) is True
    assert backend.read_setting(doc, SETTINGS["window.opacity"]) is None


def test_delete_missing_setting_returns_false(backend: AlacrittyBackend) -> None:
    doc = tomlkit.document()
    assert backend.delete_setting(doc, SETTINGS["window.opacity"]) is False


def test_delete_setting_cleans_empty_parents(backend: AlacrittyBackend) -> None:
    """Borrar el unico key de una tabla intermedia debe borrar tambien
    la tabla. Asi el archivo no queda con `[window.padding]` vacio."""
    doc = _doc_from('[window.padding]\nx = 8\n')
    backend.delete_setting(doc, SETTINGS["window.padding.x"])
    # window.padding ya no debe existir; window tampoco si quedo vacia.
    assert "window" not in doc or "padding" not in doc.get("window", {})


def test_delete_preserves_siblings(backend: AlacrittyBackend) -> None:
    """Borrar `padding.x` no debe tocar `padding.y`."""
    doc = _doc_from('[window.padding]\nx = 8\ny = 12\n')
    backend.delete_setting(doc, SETTINGS["window.padding.x"])
    assert backend.read_setting(doc, SETTINGS["window.padding.y"]) == 12


# ---------- supported_settings ----------


def test_supported_settings_count(backend: AlacrittyBackend) -> None:
    settings = backend.supported_settings()
    assert len(settings) == 6
    names = {s.name for s in settings}
    assert names == {
        "window.padding.x",
        "window.padding.y",
        "window.opacity",
        "font.size",
        "font.family",
        "cursor.shape",
    }
