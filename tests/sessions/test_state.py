"""Tests del store de `last_layout`."""

from __future__ import annotations

from pathlib import Path

import pytest

from ztc.sessions.services import state


@pytest.fixture
def tmp_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    return tmp_path


def test_get_last_layout_empty(tmp_cache: Path) -> None:
    assert state.get_last_layout() is None


def test_set_then_get(tmp_cache: Path) -> None:
    state.set_last_layout("dev")
    assert state.get_last_layout() == "dev"


def test_overwrite_preserves_other_keys(tmp_cache: Path) -> None:
    state.write_state({"last_layout": "dev", "other": "x"})
    state.set_last_layout("oscar")
    full = state.read_state()
    assert full["last_layout"] == "oscar"
    assert full["other"] == "x"


def test_corrupt_json_returns_empty(tmp_cache: Path) -> None:
    p = state.state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not valid json", encoding="utf-8")
    assert state.read_state() == {}
    assert state.get_last_layout() is None
