from __future__ import annotations

import subprocess
from typing import Any

import pytest

from term_config_tui.services import zellij_session


def _fake_completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_parse_line_running_with_metadata() -> None:
    s = zellij_session._parse_line("main [Created 14m 4s ago]")
    assert s is not None
    assert s.name == "main"
    assert s.state == "running"


def test_parse_line_just_name() -> None:
    s = zellij_session._parse_line("solo")
    assert s is not None
    assert s.name == "solo"
    assert s.state == "running"


def test_parse_line_exited() -> None:
    s = zellij_session._parse_line("EXITED - viejo [Created 1h ago]")
    assert s is not None
    assert s.name == "viejo"
    assert s.state == "exited"


def test_strip_ansi() -> None:
    raw = "\x1b[32;1mmain\x1b[m [Created 14m 4s ago]"
    assert zellij_session._strip_ansi(raw) == "main [Created 14m 4s ago]"


def test_list_sessions_parses_running(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _fake_completed(stdout="main [Created 14m 4s ago]\nwork [Created 1h ago]\n")

    monkeypatch.setattr(zellij_session.subprocess, "run", fake_run)
    monkeypatch.setattr(zellij_session, "_zellij", lambda: "/usr/bin/zellij")
    monkeypatch.delenv("ZELLIJ_SESSION_NAME", raising=False)

    sessions = zellij_session.list_sessions()
    assert [s.name for s in sessions] == ["main", "work"]
    assert all(s.state == "running" for s in sessions)
    assert all(not s.is_current for s in sessions)


def test_list_sessions_marks_current(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _fake_completed(stdout="main [Created 14m 4s ago]\n")

    monkeypatch.setattr(zellij_session.subprocess, "run", fake_run)
    monkeypatch.setattr(zellij_session, "_zellij", lambda: "/usr/bin/zellij")
    monkeypatch.setenv("ZELLIJ_SESSION_NAME", "main")

    sessions = zellij_session.list_sessions()
    assert sessions[0].is_current is True


def test_list_sessions_handles_no_active(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _fake_completed(stderr="No active zellij sessions found.\n")

    monkeypatch.setattr(zellij_session.subprocess, "run", fake_run)
    monkeypatch.setattr(zellij_session, "_zellij", lambda: "/usr/bin/zellij")
    monkeypatch.delenv("ZELLIJ_SESSION_NAME", raising=False)

    assert zellij_session.list_sessions() == []


def test_list_sessions_returns_empty_if_zellij_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(zellij_session, "_zellij", lambda: None)
    assert zellij_session.list_sessions() == []


def test_attach_argv() -> None:
    assert zellij_session.attach_argv("main") == ["zellij", "attach", "main"]


def test_new_session_argv_no_layout() -> None:
    assert zellij_session.new_session_argv("dev") == ["zellij", "-s", "dev"]


def test_new_session_argv_with_layout() -> None:
    assert zellij_session.new_session_argv("dev", layout="tablet") == [
        "zellij",
        "-n",
        "tablet",
        "-s",
        "dev",
    ]


def test_kill_session_uses_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        return _fake_completed(stdout="killed", returncode=0)

    monkeypatch.setattr(zellij_session.subprocess, "run", fake_run)
    monkeypatch.setattr(zellij_session, "_zellij", lambda: "/usr/bin/zellij")

    ok, out = zellij_session.kill_session("main")
    assert ok is True
    assert "killed" in out
    assert captured["argv"] == ["zellij", "kill-session", "main"]


def test_delete_session_force_appends_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        return _fake_completed(returncode=0)

    monkeypatch.setattr(zellij_session.subprocess, "run", fake_run)
    monkeypatch.setattr(zellij_session, "_zellij", lambda: "/usr/bin/zellij")

    zellij_session.delete_session("main", force=True)
    assert captured["argv"] == ["zellij", "delete-session", "-f", "main"]


def test_delete_session_no_force(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        return _fake_completed(returncode=1, stderr="error\n")

    monkeypatch.setattr(zellij_session.subprocess, "run", fake_run)
    monkeypatch.setattr(zellij_session, "_zellij", lambda: "/usr/bin/zellij")

    ok, out = zellij_session.delete_session("main")
    assert ok is False
    assert captured["argv"] == ["zellij", "delete-session", "main"]
    assert "error" in out


def test_inside_zellij_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZELLIJ", raising=False)
    monkeypatch.delenv("ZELLIJ_SESSION_NAME", raising=False)
    assert zellij_session.is_inside_zellij() is False
    assert zellij_session.current_session_name() is None

    monkeypatch.setenv("ZELLIJ", "0")
    monkeypatch.setenv("ZELLIJ_SESSION_NAME", "main")
    assert zellij_session.is_inside_zellij() is True
    assert zellij_session.current_session_name() == "main"
