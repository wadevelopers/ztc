from __future__ import annotations

import shutil
from pathlib import Path

from ztc.services import theme_sync
from ztc.services.save_helper import SaveResult
from ztc.services.terminals.alacritty import AlacrittyBackend

ALA_FIX = Path(__file__).parent / "fixtures" / "alacritty"


def _make_alacritty(tmp_path: Path) -> Path:
    dst = tmp_path / "alacritty.toml"
    shutil.copy2(ALA_FIX / "alacritty_min.toml", dst)
    return dst


def _empty_zellij_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.kdl"
    cfg.write_text("// empty\n", encoding="utf-8")
    return cfg


def _read(backend: AlacrittyBackend, path: Path, slot: tuple[str, str]) -> str | None:
    return backend.read_slot(backend.load(path), slot)


def test_sync_from_bundled_dracula(tmp_path: Path) -> None:
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    backend = AlacrittyBackend()
    result = theme_sync.sync_terminal_with_zellij_theme(
        zellij_theme_name="dracula",
        backend=backend,
        backend_path=ala,
        zellij_config_path=cfg,
    )
    assert result.skipped_reason is None
    assert result.backup is not None
    # Mapping 1:1 Paleta ANSI -> Alacritty. fg <- ribbon_un.background
    # (#f8f8f2 en dracula); white <- text_un.base (#ffffff).
    assert _read(backend, ala, ("primary", "background")) == "#000000"
    assert _read(backend, ala, ("primary", "foreground")) == "#f8f8f2"
    assert _read(backend, ala, ("normal", "white")) == "#ffffff"
    assert _read(backend, ala, ("normal", "red")) == "#ff5555"


def test_sync_from_user_theme(tmp_path: Path) -> None:
    ala = _make_alacritty(tmp_path)
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n'
        '    mio {\n'
        '        fg "#abcdef"\n'
        '        bg "#123456"\n'
        '        white "#dddddd"\n'
        '        red "#ff0000"\n'
        '        green "#00ff00"\n'
        '    }\n'
        '}\n',
        encoding="utf-8",
    )
    backend = AlacrittyBackend()
    result = theme_sync.sync_terminal_with_zellij_theme(
        zellij_theme_name="mio",
        backend=backend,
        backend_path=ala,
        zellij_config_path=cfg,
    )
    assert result.skipped_reason is None
    assert _read(backend, ala, ("primary", "background")) == "#123456"
    # Mapping 1:1: primary.foreground <- legacy fg.
    assert _read(backend, ala, ("primary", "foreground")) == "#abcdef"
    assert _read(backend, ala, ("normal", "white")) == "#dddddd"
    assert _read(backend, ala, ("normal", "red")) == "#ff0000"
    assert _read(backend, ala, ("normal", "green")) == "#00ff00"


def test_sync_only_writes_changed_slots(tmp_path: Path) -> None:
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    backend = AlacrittyBackend()
    # Pre-set primary.background al MISMO valor que pondria dracula
    # (sin override, bg = text_unselected.background = #000000).
    doc = backend.load(ala)
    backend.write_slot(doc, ("primary", "background"), "#000000")
    backend.save(doc, ala)

    result = theme_sync.sync_terminal_with_zellij_theme(
        zellij_theme_name="dracula",
        backend=backend,
        backend_path=ala,
        zellij_config_path=cfg,
    )
    # Aunque haya otros slots a actualizar, primary.background NO debe estar
    # en la lista de updated (ya estaba con el valor correcto).
    assert ("primary", "background") not in result.updated
    # Pero otros si.
    assert ("primary", "foreground") in result.updated


def test_sync_no_alacritty_file(tmp_path: Path) -> None:
    cfg = _empty_zellij_config(tmp_path)
    ala = tmp_path / "no.toml"
    backend = AlacrittyBackend()
    result = theme_sync.sync_terminal_with_zellij_theme(
        zellij_theme_name="dracula",
        backend=backend,
        backend_path=ala,
        zellij_config_path=cfg,
    )
    assert result.skipped_reason and "does not exist" in result.skipped_reason
    assert not result.updated


def test_sync_unknown_theme(tmp_path: Path) -> None:
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    backend = AlacrittyBackend()
    result = theme_sync.sync_terminal_with_zellij_theme(
        zellij_theme_name="nonexistent-theme-name",
        backend=backend,
        backend_path=ala,
        zellij_config_path=cfg,
    )
    assert result.skipped_reason and "no extractable colors" in result.skipped_reason
    assert not result.updated


def test_sync_no_changes_returns_no_backup(tmp_path: Path) -> None:
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    backend = AlacrittyBackend()
    # Aplicar dracula una vez.
    theme_sync.sync_terminal_with_zellij_theme(
        zellij_theme_name="dracula",
        backend=backend,
        backend_path=ala,
        zellij_config_path=cfg,
    )
    # Aplicar de nuevo: nada deberia cambiar.
    result = theme_sync.sync_terminal_with_zellij_theme(
        zellij_theme_name="dracula",
        backend=backend,
        backend_path=ala,
        zellij_config_path=cfg,
    )
    assert result.backup is None
    assert result.updated == {}
    assert result.skipped_reason == "No changes"


def test_sync_propagates_text_selected_to_alacritty_selection(tmp_path: Path) -> None:
    """El bg/text de la seleccion en alacritty se sincroniza desde
    text_selected.{background,base} del .kdl Zellij."""
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    backend = AlacrittyBackend()
    # ayu-dark tiene text_selected.background = #475266 y .base = #cccac2.
    theme_sync.sync_terminal_with_zellij_theme(
        zellij_theme_name="ayu-dark",
        backend=backend,
        backend_path=ala,
        zellij_config_path=cfg,
    )
    assert _read(backend, ala, ("selection", "background")) == "#475266"
    assert _read(backend, ala, ("selection", "text")) == "#cccac2"


def test_sync_user_theme_with_rich_components(tmp_path: Path) -> None:
    """Si un user theme tiene raw_components, sus text_selected.* van
    a alacritty.selection.*."""
    cfg = tmp_path / "config.kdl"
    cfg.write_text(
        'themes {\n'
        '    mio {\n'
        '        fg "#aaaaaa"\n'
        '        bg "#111111"\n'
        '        text_selected {\n'
        '            base "#ffffff"\n'
        '            background "#5566aa"\n'
        '        }\n'
        '    }\n'
        '}\n',
        encoding="utf-8",
    )
    ala = _make_alacritty(tmp_path)
    backend = AlacrittyBackend()
    theme_sync.sync_terminal_with_zellij_theme(
        zellij_theme_name="mio",
        backend=backend,
        backend_path=ala,
        zellij_config_path=cfg,
    )
    assert _read(backend, ala, ("selection", "background")) == "#5566aa"
    assert _read(backend, ala, ("selection", "text")) == "#ffffff"


def test_sync_preserves_other_alacritty_sections(tmp_path: Path) -> None:
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    backend = AlacrittyBackend()
    theme_sync.sync_terminal_with_zellij_theme(
        zellij_theme_name="dracula",
        backend=backend,
        backend_path=ala,
        zellij_config_path=cfg,
    )
    text = ala.read_text(encoding="utf-8")
    # Las secciones que no son colors no se tocan.
    assert "[window]" in text
    assert "padding" in text
    assert "opacity" in text


def test_sync_result_includes_reload_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    backend = AlacrittyBackend()
    calls: list[tuple[object, object, Path]] = []

    def fake_save_with_reload(backend_arg, doc_arg, path_arg):  # noqa: ANN001
        calls.append((backend_arg, doc_arg, path_arg))
        return SaveResult(
            backup_path=tmp_path / "alacritty.toml.bak",
            reload_ok=False,
            manual_reload_hint="manual hint",
        )

    monkeypatch.setattr(theme_sync, "save_with_reload", fake_save_with_reload)
    result = theme_sync.sync_terminal_with_zellij_theme(
        zellij_theme_name="dracula",
        backend=backend,
        backend_path=ala,
        zellij_config_path=cfg,
    )
    assert len(calls) == 1
    assert result.backup == tmp_path / "alacritty.toml.bak"
    assert result.reload_ok is False
    assert result.manual_reload_hint == "manual hint"


def test_sync_uses_save_profile_with_reload_when_manifest_path_given(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Cuando se pasa `manifest_path`, debe ir por `save_profile_with_reload`
    (no `save_with_reload`). Necesario en Kitty con manifest para que el
    reload IPC lea las prefs runtime del manifest."""
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    backend = AlacrittyBackend()
    profile_calls: list[tuple[object, object, Path, Path]] = []
    plain_calls: list[tuple[object, object, Path]] = []

    def fake_save_profile_with_reload(  # noqa: ANN001
        backend_arg, doc_arg, profile_path, manifest_path
    ):
        profile_calls.append((backend_arg, doc_arg, profile_path, manifest_path))
        return SaveResult(
            backup_path=tmp_path / "alacritty.toml.bak",
            reload_ok=True,
            manual_reload_hint=None,
        )

    def fake_save_with_reload(backend_arg, doc_arg, path_arg):  # noqa: ANN001
        plain_calls.append((backend_arg, doc_arg, path_arg))
        return SaveResult(backup_path=None, reload_ok=True, manual_reload_hint=None)

    monkeypatch.setattr(
        theme_sync, "save_profile_with_reload", fake_save_profile_with_reload
    )
    monkeypatch.setattr(theme_sync, "save_with_reload", fake_save_with_reload)

    manifest_path = tmp_path / "alacritty.manifest.toml"
    theme_sync.sync_terminal_with_zellij_theme(
        zellij_theme_name="dracula",
        backend=backend,
        backend_path=ala,
        zellij_config_path=cfg,
        manifest_path=manifest_path,
    )
    assert len(profile_calls) == 1
    assert profile_calls[0][2] == ala
    assert profile_calls[0][3] == manifest_path
    assert plain_calls == []  # no debe llamar al helper sin manifest


def test_sync_falls_back_to_save_with_reload_when_no_manifest_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Sin `manifest_path` (default None), comportamiento clasico: usa
    `save_with_reload`. Compat con callers que aun no conocen el concepto."""
    ala = _make_alacritty(tmp_path)
    cfg = _empty_zellij_config(tmp_path)
    backend = AlacrittyBackend()
    profile_calls: list[object] = []
    plain_calls: list[object] = []

    def fake_save_profile_with_reload(*args, **kwargs):  # noqa: ANN001, ANN003
        profile_calls.append((args, kwargs))
        return SaveResult(backup_path=None, reload_ok=True, manual_reload_hint=None)

    def fake_save_with_reload(*args, **kwargs):  # noqa: ANN001, ANN003
        plain_calls.append((args, kwargs))
        return SaveResult(backup_path=None, reload_ok=True, manual_reload_hint=None)

    monkeypatch.setattr(
        theme_sync, "save_profile_with_reload", fake_save_profile_with_reload
    )
    monkeypatch.setattr(theme_sync, "save_with_reload", fake_save_with_reload)

    theme_sync.sync_terminal_with_zellij_theme(
        zellij_theme_name="dracula",
        backend=backend,
        backend_path=ala,
        zellij_config_path=cfg,
        # manifest_path default = None
    )
    assert len(plain_calls) == 1
    assert profile_calls == []
