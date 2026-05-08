"""Tests del parser de `zellij list-sessions` y del helper de nombres default."""

from __future__ import annotations

from ztc.sessions.services.zellij_session import _parse_line, next_default_name


def test_parse_running_session() -> None:
    s = _parse_line("main [Created 14m 4s ago]")
    assert s is not None
    assert s.name == "main"
    assert s.state == "running"


def test_parse_running_with_current_marker() -> None:
    s = _parse_line("main [Created 14m 4s ago] (current)")
    assert s is not None
    assert s.name == "main"
    assert s.state == "running"


def test_parse_exited_inline_suffix() -> None:
    s = _parse_line("work [Created 2d ago] (EXITED - attach to resurrect)")
    assert s is not None
    assert s.name == "work"
    assert s.state == "exited"


def test_parse_exited_legacy_prefix() -> None:
    s = _parse_line("EXITED - old [Created ...]")
    assert s is not None
    assert s.name == "old"
    assert s.state == "exited"


def test_parse_just_name() -> None:
    s = _parse_line("solo-name")
    assert s is not None
    assert s.name == "solo-name"
    assert s.state == "running"


def test_next_default_name_empty() -> None:
    assert next_default_name(set()) == "main"


def test_next_default_name_increments() -> None:
    assert next_default_name({"main"}) == "main2"
    assert next_default_name({"main", "main2"}) == "main3"
    assert next_default_name({"main", "main2", "main3", "main4"}) == "main5"


def test_next_default_name_skips_only_main_chain() -> None:
    """Si hay sesiones con otros nombres pero no `main`, el default vuelve a `main`."""
    assert next_default_name({"work", "dev"}) == "main"
