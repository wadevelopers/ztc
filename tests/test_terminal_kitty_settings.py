"""Tests del backend Kitty para settings. Cubre:
- Roundtrip read→write→read de los 6 settings.
- Caso especial `window_padding_width` (1/2/3/4 valores; simetrico vs
  asimetrico; int vs float).
- font_family con espacios (Kitty no usa comillas).
- delete y resoluciones via includes (last-wins).
- Errores controlados al write con valor invalido (ValueError).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ztc.services.terminals.kitty import KittyBackend, KittyDoc
from ztc.services.terminals.settings import SETTINGS


@pytest.fixture
def backend() -> KittyBackend:
    return KittyBackend()


def _doc_from(tmp_path: Path, lines: list[str]) -> KittyDoc:
    """Crea un KittyDoc con archivo en disco (necesario para resolver
    `include` relativos en `_linearize`)."""
    path = tmp_path / "kitty.conf"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return KittyDoc(path=path, lines=list(lines))


# ---------- read directos (settings sin caso especial) ----------


def test_read_opacity(backend: KittyBackend, tmp_path: Path) -> None:
    doc = _doc_from(tmp_path, ["background_opacity 0.85"])
    assert backend.read_setting(doc, SETTINGS["window.opacity"]) == 0.85


def test_read_font_size(backend: KittyBackend, tmp_path: Path) -> None:
    doc = _doc_from(tmp_path, ["font_size 14.0"])
    assert backend.read_setting(doc, SETTINGS["font.size"]) == 14.0


def test_read_font_family_with_spaces(backend: KittyBackend, tmp_path: Path) -> None:
    """Kitty no usa comillas: `font_family JetBrains Mono` debe leerse
    con los espacios incluidos."""
    doc = _doc_from(tmp_path, ["font_family JetBrains Mono"])
    assert (
        backend.read_setting(doc, SETTINGS["font.family"]) == "JetBrains Mono"
    )


def test_read_cursor_shape_normalized(backend: KittyBackend, tmp_path: Path) -> None:
    """Kitty acepta minusculas (`block`); el coerce devuelve la forma
    canonica capitalizada (`Block`)."""
    doc = _doc_from(tmp_path, ["cursor_shape block"])
    assert backend.read_setting(doc, SETTINGS["cursor.shape"]) == "Block"


# ---------- read: window_padding_width con 1/2/3/4 valores ----------


def test_padding_1_value(backend: KittyBackend, tmp_path: Path) -> None:
    """1 valor aplica a los 4 lados → x e y son ese valor."""
    doc = _doc_from(tmp_path, ["window_padding_width 5"])
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) == 5
    assert backend.read_setting(doc, SETTINGS["window.padding.y"]) == 5


def test_padding_2_values_vertical_horizontal(
    backend: KittyBackend, tmp_path: Path
) -> None:
    """2 valores: vertical(y) horizontal(x) → primer valor es y, segundo es x."""
    doc = _doc_from(tmp_path, ["window_padding_width 10 20"])
    assert backend.read_setting(doc, SETTINGS["window.padding.y"]) == 10
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) == 20


def test_padding_3_values_symmetric_top_bottom(
    backend: KittyBackend, tmp_path: Path
) -> None:
    """3 valores (top horizontal bottom): si top==bottom, y representable;
    x siempre representable (es horizontal explicito)."""
    doc = _doc_from(tmp_path, ["window_padding_width 10 20 10"])
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) == 20
    assert backend.read_setting(doc, SETTINGS["window.padding.y"]) == 10


def test_padding_3_values_asymmetric_returns_none_for_y(
    backend: KittyBackend, tmp_path: Path
) -> None:
    """3 valores asimetricos en y (top != bottom) → y no representable, None."""
    doc = _doc_from(tmp_path, ["window_padding_width 10 20 15"])
    assert backend.read_setting(doc, SETTINGS["window.padding.y"]) is None
    # x sigue siendo el valor central (horizontal).
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) == 20


def test_padding_4_values_symmetric(
    backend: KittyBackend, tmp_path: Path
) -> None:
    """4 valores (top right bottom left): simetrico si top==bottom y left==right."""
    doc = _doc_from(tmp_path, ["window_padding_width 10 20 10 20"])
    assert backend.read_setting(doc, SETTINGS["window.padding.y"]) == 10
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) == 20


def test_padding_4_values_asymmetric_returns_none(
    backend: KittyBackend, tmp_path: Path
) -> None:
    """4 valores asimetricos en cualquier eje → None en ese eje."""
    # top != bottom → y no representable
    doc = _doc_from(tmp_path, ["window_padding_width 10 20 15 20"])
    assert backend.read_setting(doc, SETTINGS["window.padding.y"]) is None
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) == 20

    # left != right → x no representable
    doc2 = _doc_from(tmp_path, ["window_padding_width 10 20 10 25"])
    assert backend.read_setting(doc2, SETTINGS["window.padding.y"]) == 10
    assert backend.read_setting(doc2, SETTINGS["window.padding.x"]) is None


def test_padding_with_float_returns_none(
    backend: KittyBackend, tmp_path: Path
) -> None:
    """Kitty acepta floats en pts pero el canon es int. `2.5` → None
    (la UI muestra unset hasta que el usuario sobreescriba)."""
    doc = _doc_from(tmp_path, ["window_padding_width 2.5"])
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) is None
    assert backend.read_setting(doc, SETTINGS["window.padding.y"]) is None


def test_padding_with_clean_float_returns_int(
    backend: KittyBackend, tmp_path: Path
) -> None:
    """Floats enteros (`5.0`) se aceptan como int (5)."""
    doc = _doc_from(tmp_path, ["window_padding_width 5.0"])
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) == 5


# ---------- write: roundtrip ----------


def test_write_padding_emits_2_values_y_x(
    backend: KittyBackend, tmp_path: Path
) -> None:
    """Write siempre emite `window_padding_width Y X` (vertical horizontal)."""
    doc = _doc_from(tmp_path, [])
    backend.write_setting(doc, SETTINGS["window.padding.x"], 20)
    backend.write_setting(doc, SETTINGS["window.padding.y"], 10)
    # Tras los dos writes, debe quedar 1 sola linea.
    padding_lines = [li for li in doc.lines if li.startswith("window_padding_width")]
    assert len(padding_lines) == 1
    assert padding_lines[0] == "window_padding_width 10 20"


def test_write_padding_overwrites_4_values(
    backend: KittyBackend, tmp_path: Path
) -> None:
    """Write sobre archivo con 4 valores asimetricos sobreescribe a 2 valores."""
    doc = _doc_from(tmp_path, ["window_padding_width 10 20 15 25"])
    backend.write_setting(doc, SETTINGS["window.padding.x"], 30)
    # Lee la y original (top=10, antes era asimetrica → None) — pero
    # write tiene que componer: la y no representable cae a 0 (default
    # implicito si current_y=0); el usuario eligio editar x sin mirar y.
    assert "window_padding_width" in doc.lines[0]
    # Verificacion mas robusta: leer los nuevos valores.
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) == 30


def test_write_then_read_opacity(backend: KittyBackend, tmp_path: Path) -> None:
    doc = _doc_from(tmp_path, [])
    backend.write_setting(doc, SETTINGS["window.opacity"], 0.7)
    assert backend.read_setting(doc, SETTINGS["window.opacity"]) == 0.7


def test_write_overwrites_existing_entry(
    backend: KittyBackend, tmp_path: Path
) -> None:
    """Si el setting ya esta en el main, write actualiza in-place (no appendea)."""
    doc = _doc_from(tmp_path, ["font_size 12.0"])
    backend.write_setting(doc, SETTINGS["font.size"], 16.0)
    sizes = [li for li in doc.lines if li.startswith("font_size")]
    assert len(sizes) == 1
    assert sizes[0] == "font_size 16.0"


def test_write_appends_when_in_include_only(
    backend: KittyBackend, tmp_path: Path
) -> None:
    """Si la entrada solo viene de un include, write appendea al main."""
    inc = tmp_path / "theme.conf"
    inc.write_text("font_size 14.0\n", encoding="utf-8")
    doc = _doc_from(tmp_path, ["include theme.conf"])
    backend.write_setting(doc, SETTINGS["font.size"], 16.0)
    # main ahora tiene include + nueva linea.
    assert any(li == "font_size 16.0" for li in doc.lines)
    # el include no se toca.
    assert inc.read_text() == "font_size 14.0\n"


# ---------- write: invalid values raise ValueError ----------


def test_write_invalid_padding_raises(backend: KittyBackend, tmp_path: Path) -> None:
    doc = _doc_from(tmp_path, [])
    with pytest.raises(ValueError):
        backend.write_setting(doc, SETTINGS["window.padding.x"], -5)


def test_write_invalid_opacity_raises(backend: KittyBackend, tmp_path: Path) -> None:
    doc = _doc_from(tmp_path, [])
    with pytest.raises(ValueError):
        backend.write_setting(doc, SETTINGS["window.opacity"], 2.0)


def test_write_invalid_enum_raises(backend: KittyBackend, tmp_path: Path) -> None:
    doc = _doc_from(tmp_path, [])
    with pytest.raises(ValueError):
        backend.write_setting(doc, SETTINGS["cursor.shape"], "Diamond")


# ---------- delete ----------


def test_delete_removes_main_entry(backend: KittyBackend, tmp_path: Path) -> None:
    doc = _doc_from(tmp_path, ["font_size 14.0", "background_opacity 0.8"])
    assert backend.delete_setting(doc, SETTINGS["window.opacity"]) is True
    assert backend.read_setting(doc, SETTINGS["window.opacity"]) is None
    # font_size sigue ahi.
    assert backend.read_setting(doc, SETTINGS["font.size"]) == 14.0


def test_delete_padding_removes_shared_line(
    backend: KittyBackend, tmp_path: Path
) -> None:
    """`window.padding.x` y `padding.y` comparten `window_padding_width`.
    Borrar cualquiera elimina la linea entera (no podemos borrar solo una
    direccion)."""
    doc = _doc_from(tmp_path, ["window_padding_width 10 20"])
    assert backend.delete_setting(doc, SETTINGS["window.padding.x"]) is True
    assert backend.read_setting(doc, SETTINGS["window.padding.x"]) is None
    assert backend.read_setting(doc, SETTINGS["window.padding.y"]) is None


def test_delete_missing_returns_false(backend: KittyBackend, tmp_path: Path) -> None:
    doc = _doc_from(tmp_path, [])
    assert backend.delete_setting(doc, SETTINGS["font.size"]) is False


# ---------- supported_settings ----------


def test_supported_settings_count(backend: KittyBackend) -> None:
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
