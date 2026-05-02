from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from textual.widgets import OptionList

from term_config_tui.app import TermConfigApp
from term_config_tui.models.config import Paths
from term_config_tui.models.session import ZellijSession
from term_config_tui.screens.session_manager import SessionManagerScreen
from term_config_tui.services import zellij_session
from term_config_tui.widgets.confirm import ConfirmByNameModal


def _paths(tmp_path: Path) -> Paths:
    return Paths(
        zellij_config=tmp_path / "config.kdl",
        zellij_layouts_dir=tmp_path / "layouts",
        alacritty_config=tmp_path / "alacritty.toml",
    )


async def test_session_manager_lists_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = [
        ZellijSession(name="main", state="running", is_current=True),
        ZellijSession(name="work", state="running"),
    ]
    monkeypatch.setattr(zellij_session, "list_sessions", lambda: fake)

    app = TermConfigApp(paths=_paths(tmp_path))
    async with app.run_test() as pilot:
        # Navegar al item "Sesiones Zellij" en el menu (segundo item).
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SessionManagerScreen)
        option_list = screen.query_one("#session-list", OptionList)
        ids = [
            option_list.get_option_at_index(i).id
            for i in range(option_list.option_count)
        ]
        assert ids == ["main", "work"]


async def test_session_manager_kill_with_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        zellij_session,
        "list_sessions",
        lambda: [ZellijSession(name="work", state="running")],
    )
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.setdefault("calls", []).append(argv)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(zellij_session.subprocess, "run", fake_run)
    monkeypatch.setattr(zellij_session, "_zellij", lambda: "/usr/bin/zellij")

    app = TermConfigApp(paths=_paths(tmp_path))
    async with app.run_test() as pilot:
        await pilot.press("down", "enter")
        await pilot.pause()
        # Disparar kill: aparece el modal.
        await pilot.press("k")
        await pilot.pause()
        modal = app.screen
        assert isinstance(modal, ConfirmByNameModal)
        # Escribir el nombre y confirmar con Enter.
        for ch in "work":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()

    calls = captured.get("calls", [])
    kill_calls = [c for c in calls if "kill-session" in c]
    assert kill_calls == [["zellij", "kill-session", "work"]]


async def test_session_manager_kill_cancel_does_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        zellij_session,
        "list_sessions",
        lambda: [ZellijSession(name="work", state="running")],
    )
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.setdefault("calls", []).append(argv)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(zellij_session.subprocess, "run", fake_run)
    monkeypatch.setattr(zellij_session, "_zellij", lambda: "/usr/bin/zellij")

    app = TermConfigApp(paths=_paths(tmp_path))
    async with app.run_test() as pilot:
        await pilot.press("down", "enter")
        await pilot.pause()
        await pilot.press("k")
        await pilot.pause()
        # Escribir mal el nombre y pulsar Enter: el modal NO debe confirmar.
        for ch in "wro":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        # Cancelar con Escape.
        await pilot.press("escape")
        await pilot.pause()

    kill_calls = [c for c in captured.get("calls", []) if "kill-session" in c]
    assert kill_calls == []


async def test_session_manager_blocks_kill_of_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        zellij_session,
        "list_sessions",
        lambda: [ZellijSession(name="main", state="running", is_current=True)],
    )
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.setdefault("calls", []).append(argv)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(zellij_session.subprocess, "run", fake_run)

    app = TermConfigApp(paths=_paths(tmp_path))
    async with app.run_test() as pilot:
        await pilot.press("down", "enter")
        await pilot.pause()
        await pilot.press("k")
        await pilot.pause()
        # No debe haber abierto modal: la sesion actual esta protegida.
        assert not isinstance(app.screen, ConfirmByNameModal)

    assert "calls" not in captured
