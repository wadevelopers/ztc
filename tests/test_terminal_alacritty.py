from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import tomlkit

from ztc.services import colors
from ztc.services.terminals.alacritty import (
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


def test_compute_warnings_clean_when_high_contrast() -> None:
    backend = AlacrittyBackend()
    doc = tomlkit.document()
    backend.write_slot(doc, ("primary", "background"), "#000000")
    backend.write_slot(doc, ("primary", "foreground"), "#ffffff")
    backend.write_slot(doc, ("normal", "black"), "#aaaaaa")
    backend.write_slot(doc, ("selection", "background"), "#888888")
    backend.write_slot(doc, ("cursor", "cursor"), "#ffaa00")
    assert colors.compute_warnings(_slots_from_doc(backend, doc)) == []


# ---------- perfiles intercambiables (manifest + profile switching) ----------


def _write_manifest(path: Path, profile_name: str) -> None:
    """Helper: crea un manifest minimal apuntando a `profile_name`."""
    path.write_text(
        "# ztc-managed-manifest = true\n\n"
        f'import = ["{profile_name}"]\n',
        encoding="utf-8",
    )


def _write_legacy_manifest(path: Path, profile_name: str) -> None:
    path.write_text(
        "[ztc]\nmanaged_manifest = true\n\n"
        f'[general]\nimport = ["{profile_name}"]\n',
        encoding="utf-8",
    )


def _mock_alacritty_version(
    monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    class Result:
        stdout = f"alacritty {version}"
        stderr = ""

    monkeypatch.setattr(
        "ztc.services.terminals.alacritty.subprocess.run",
        lambda *args, **kwargs: Result(),
    )


def test_is_managed_manifest_false_for_standalone(tmp_path: Path) -> None:
    """Una config sin marker ztc no es manifest, aunque tenga imports."""
    backend = AlacrittyBackend()
    path = tmp_path / "alacritty.toml"
    path.write_text(
        '[general]\nimport = ["theme.toml"]\n[window]\nopacity = 0.9\n',
        encoding="utf-8",
    )
    assert backend.is_managed_manifest(path) is False


def test_is_managed_manifest_false_for_missing_file(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    assert backend.is_managed_manifest(tmp_path / "missing.toml") is False


def test_is_managed_manifest_true_when_marker_present(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    path = tmp_path / "alacritty.toml"
    _write_manifest(path, "c64.toml")
    assert backend.is_managed_manifest(path) is True


def test_is_managed_manifest_true_for_legacy_ztc_table(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    path = tmp_path / "alacritty.toml"
    _write_legacy_manifest(path, "c64.toml")
    assert backend.is_managed_manifest(path) is True


def test_read_active_profile_returns_none_when_not_manifest(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    path = tmp_path / "alacritty.toml"
    path.write_text(
        '[general]\nimport = ["theme.toml"]\n', encoding="utf-8"
    )
    assert backend.read_active_profile(path) is None


def test_read_active_profile_returns_relative_path(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    manifest = tmp_path / "alacritty.toml"
    _write_manifest(manifest, "c64.toml")
    assert backend.read_active_profile(manifest) == tmp_path / "c64.toml"


def test_read_active_profile_accepts_legacy_general_import(
    tmp_path: Path,
) -> None:
    backend = AlacrittyBackend()
    manifest = tmp_path / "alacritty.toml"
    _write_legacy_manifest(manifest, "c64.toml")
    assert backend.read_active_profile(manifest) == tmp_path / "c64.toml"


def test_read_active_profile_handles_absolute_path(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    manifest = tmp_path / "alacritty.toml"
    abs_profile = tmp_path / "other" / "c64.toml"
    manifest.write_text(
        "# ztc-managed-manifest = true\n\n"
        f'import = ["{abs_profile}"]\n',
        encoding="utf-8",
    )
    assert backend.read_active_profile(manifest) == abs_profile


def test_write_active_profile_uses_root_import_for_alacritty_0_13(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_alacritty_version(monkeypatch, "0.13.2")
    # Alacritty requiere paths `~/...` o absolutos en `import`. Simular
    # que tmp_path es el home del usuario para que el path emitido
    # quede como `~/vga.toml` (camino realista en producción).
    monkeypatch.setenv("HOME", str(tmp_path))
    backend = AlacrittyBackend()
    manifest = tmp_path / "alacritty.toml"
    _write_manifest(manifest, "c64.toml")
    backend.write_active_profile(manifest, tmp_path / "vga.toml")
    text = manifest.read_text(encoding="utf-8")
    assert backend.is_managed_manifest(manifest) is True
    assert backend.read_active_profile(manifest) == tmp_path / "vga.toml"
    assert "# ztc-managed-manifest = true" in text
    assert 'import = ["~/vga.toml"]' in text
    assert "[general]" not in text
    assert "[ztc]" not in text


def test_write_active_profile_uses_general_import_for_alacritty_0_14(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_alacritty_version(monkeypatch, "0.14.0")
    monkeypatch.setenv("HOME", str(tmp_path))
    backend = AlacrittyBackend()
    manifest = tmp_path / "alacritty.toml"
    _write_manifest(manifest, "c64.toml")
    backend.write_active_profile(manifest, tmp_path / "vga.toml")
    text = manifest.read_text(encoding="utf-8")
    assert backend.is_managed_manifest(manifest) is True
    assert backend.read_active_profile(manifest) == tmp_path / "vga.toml"
    assert "# ztc-managed-manifest = true" in text
    assert "[general]" in text
    assert 'import = ["~/vga.toml"]' in text
    assert "[ztc]" not in text


def test_write_active_profile_uses_absolute_path_outside_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si el perfil está fuera de $HOME, el manifest usa path absoluto
    (`/...`). Alacritty acepta ambos formatos; el simple sin prefijo
    es el único que NO acepta."""
    _mock_alacritty_version(monkeypatch, "0.13.2")
    # HOME apunta a otro lugar; tmp_path queda fuera.
    monkeypatch.setenv("HOME", "/nonexistent-home")
    backend = AlacrittyBackend()
    manifest = tmp_path / "alacritty.toml"
    _write_manifest(manifest, "c64.toml")
    profile = tmp_path / "vga.toml"
    backend.write_active_profile(manifest, profile)
    text = manifest.read_text(encoding="utf-8")
    assert f'import = ["{profile}"]' in text


def test_convert_to_manifest_writes_minimal_manifest_with_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El archivo original se vuelve manifest minimal apuntando al
    active_profile. El contenido viejo NO se duplica en active_profile —
    queda solo en el backup. El caller es responsable de crear
    active_profile (en este test no lo creamos, solo verificamos el
    estado del manifest)."""
    backend = AlacrittyBackend()
    path = tmp_path / "alacritty.toml"
    original_text = (
        '# user comment\n'
        '[colors.primary]\n'
        'background = "#000000"\n'
        '[window]\n'
        'opacity = 0.97\n'
    )
    path.write_text(original_text, encoding="utf-8")

    active = tmp_path / "tokyo.toml"
    _mock_alacritty_version(monkeypatch, "0.13.2")
    monkeypatch.setenv("HOME", str(tmp_path))
    backup = backend.convert_to_manifest(path, active)

    # Backup creado con el contenido original.
    assert backup is not None
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == original_text
    # Active profile NO fue creado por convert_to_manifest.
    assert not active.exists()
    # Manifest pasa a ser gestionado y apunta al active.
    assert backend.is_managed_manifest(path) is True
    assert backend.read_active_profile(path) == active
    # Manifest es minimal: marker + import, sin colores/settings viejos.
    manifest_text = path.read_text(encoding="utf-8")
    assert "# ztc-managed-manifest = true" in manifest_text
    assert 'import = ["~/tokyo.toml"]' in manifest_text
    assert "[ztc]" not in manifest_text
    assert "[general]" not in manifest_text
    assert "#000000" not in manifest_text
    assert "opacity" not in manifest_text


def test_convert_to_manifest_raises_if_source_missing(tmp_path: Path) -> None:
    backend = AlacrittyBackend()
    with pytest.raises(FileNotFoundError):
        backend.convert_to_manifest(
            tmp_path / "missing.toml", tmp_path / "c64.toml"
        )
