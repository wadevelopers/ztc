from __future__ import annotations

import shutil
from pathlib import Path

from term_config_tui.services import toml_io

FIX = Path(__file__).parent / "fixtures" / "alacritty"


def test_load_and_dump_preserves_comments_and_inline_table(tmp_path: Path) -> None:
    src = FIX / "alacritty_min.toml"
    dst = tmp_path / "alacritty.toml"
    shutil.copy2(src, dst)

    doc = toml_io.load_toml(dst)
    assert doc["window"]["opacity"] == 0.97  # type: ignore[index]
    # tomlkit expone valores tipados (Float wrappers); casteamos via float() abajo.

    # Modificacion: cambiar background.
    doc["colors"]["primary"]["background"] = "#000000"  # type: ignore[index]

    backup = toml_io.dump_toml(doc, dst)
    assert backup is not None
    assert backup.exists()

    text = dst.read_text(encoding="utf-8")
    assert '#000000' in text
    # Comentario y tabla inline preservados.
    assert "# colores" in text
    assert "padding = { x = 8, y = 8 }" in text
    assert "[colors.primary]" in text
    assert "[colors.normal]" in text


def test_load_nonexistent_returns_empty_doc(tmp_path: Path) -> None:
    doc = toml_io.load_toml(tmp_path / "no.toml")
    assert len(doc) == 0


def test_dump_creates_file_when_missing(tmp_path: Path) -> None:
    import tomlkit

    doc = tomlkit.document()
    doc["a"] = 1
    target = tmp_path / "new.toml"
    backup = toml_io.dump_toml(doc, target)
    assert backup is None  # no habia archivo previo, no se hace backup
    assert target.read_text(encoding="utf-8").strip() == "a = 1"
