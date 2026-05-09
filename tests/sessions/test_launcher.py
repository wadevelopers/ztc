"""Tests del dispatcher compartido (`ztc.sessions.launcher`).

Cubre el mapeo `LaunchTarget` -> `os.execvp(...)` para los 3 casos
validos + None + accion desconocida (defense-in-depth)."""

from __future__ import annotations

from typing import cast

import pytest

from ztc.sessions import launcher
from ztc.sessions.types import LaunchTarget


def test_dispatch_target_attach_invokes_execvp(monkeypatch) -> None:
    captured: list[tuple[str, list[str]]] = []

    def fake_execvp(file: str, args: list[str]) -> None:
        captured.append((file, list(args)))
        raise SystemExit(0)  # corta el flujo, igual que execvp real

    monkeypatch.setattr("ztc.sessions.launcher.os.execvp", fake_execvp)
    with pytest.raises(SystemExit):
        launcher.dispatch_target(("attach", "mi-sesion", None))
    assert len(captured) == 1
    file, argv = captured[0]
    assert file == "zellij"
    assert "attach" in argv
    assert "mi-sesion" in argv


def test_dispatch_target_new_invokes_execvp(monkeypatch) -> None:
    captured: list[tuple[str, list[str]]] = []

    def fake_execvp(file: str, args: list[str]) -> None:
        captured.append((file, list(args)))
        raise SystemExit(0)

    monkeypatch.setattr("ztc.sessions.launcher.os.execvp", fake_execvp)
    with pytest.raises(SystemExit):
        launcher.dispatch_target(("new", "nueva", "compact"))
    assert len(captured) == 1
    file, argv = captured[0]
    assert file == "zellij"
    assert "nueva" in argv
    assert "compact" in argv


def test_dispatch_target_bash_invokes_execvp(monkeypatch) -> None:
    captured: list[tuple[str, list[str]]] = []

    def fake_execvp(file: str, args: list[str]) -> None:
        captured.append((file, list(args)))
        raise SystemExit(0)

    monkeypatch.setattr("ztc.sessions.launcher.os.execvp", fake_execvp)
    monkeypatch.setenv("SHELL", "/bin/zsh")
    with pytest.raises(SystemExit):
        launcher.dispatch_target(("bash", None, None))
    assert captured == [("/bin/zsh", ["/bin/zsh"])]


def test_dispatch_target_none_is_noop(monkeypatch) -> None:
    captured: list[tuple[str, list[str]]] = []

    def fake_execvp(file: str, args: list[str]) -> None:
        captured.append((file, list(args)))

    monkeypatch.setattr("ztc.sessions.launcher.os.execvp", fake_execvp)
    launcher.dispatch_target(None)
    assert captured == []


def test_dispatch_target_unknown_action_exits(monkeypatch) -> None:
    """Defense-in-depth: si llega una accion no contemplada (bypass del
    type system, datos dinamicos, etc.) sale con `sys.exit` y mensaje
    claro en lugar de silenciosamente no hacer nada."""
    # cast para esquivar el Literal en construccion — simulamos el
    # caso defensivo donde algo escribio basura en el target.
    bad_target = cast(LaunchTarget, ("frobnicate", None, None))
    with pytest.raises(SystemExit) as excinfo:
        launcher.dispatch_target(bad_target)
    assert "frobnicate" in str(excinfo.value)
