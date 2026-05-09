"""Tests del detector de clientes attached.

`get_attached_session_clients` corre `pgrep` y parsea su salida; los
tests inyectan output simulado mockeando `subprocess.run`. La idea es
que si Zellij cambia el formato del cmdline en una version futura,
estos tests rompen y nos enteramos.
"""

from __future__ import annotations

from unittest.mock import patch

from ztc.sessions.services.zellij_session import (
    _extract_client_session_name,
    get_attached_session_clients,
    list_sessions,
)

# ---------- _extract_client_session_name (parser puro) ----------


def test_extract_attach_name() -> None:
    assert _extract_client_session_name("zellij attach main") == "main"


def test_extract_dash_s() -> None:
    assert _extract_client_session_name("zellij -s main2") == "main2"


def test_extract_long_session() -> None:
    assert _extract_client_session_name("zellij --session work") == "work"


def test_extract_long_session_equals() -> None:
    assert _extract_client_session_name("zellij --session=work") == "work"


def test_extract_with_layout() -> None:
    assert (
        _extract_client_session_name("zellij -n compact -s main") == "main"
    )


def test_extract_returns_none_when_no_match() -> None:
    """`zellij` solo, sin args reconocibles -> no podemos saber sesion."""
    assert _extract_client_session_name("zellij") is None


def test_extract_returns_none_for_options_subcommand() -> None:
    """`zellij options ...` es un subcommand sin sesion."""
    assert _extract_client_session_name("zellij options --help") is None


# ---------- get_attached_session_clients (con pgrep mockeado) ----------


def _make_pgrep_output(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def _mock_pgrep(stdout: str):
    """Helper para mockear subprocess.run y shutil.which."""

    class _Result:
        def __init__(self, out: str) -> None:
            self.stdout = out
            self.stderr = ""
            self.returncode = 0

    return _Result(stdout)


def test_clients_counted_per_session() -> None:
    pgrep_output = _make_pgrep_output(
        [
            "808405 /home/martin/.local/bin/zellij --server "
            "/run/user/1000/zellij/contract_version_1/main",
            "808500 /home/martin/.local/bin/zellij attach main",
            "808600 /home/martin/.local/bin/zellij -s work",
        ]
    )
    with (
        patch(
            "ztc.sessions.services.zellij_session.shutil.which", return_value="/usr/bin/pgrep"
        ),
        patch(
            "ztc.sessions.services.zellij_session.subprocess.run",
            return_value=_mock_pgrep(pgrep_output),
        ),
    ):
        result = get_attached_session_clients()
    assert result == {"main": 1, "work": 1}


def test_multiple_clients_for_same_session() -> None:
    """Dos terminales attacheadas a la misma sesion = count 2."""
    pgrep_output = _make_pgrep_output(
        [
            "100 /home/martin/.local/bin/zellij attach main",
            "200 /home/martin/.local/bin/zellij attach main",
            "300 /home/martin/.local/bin/zellij --server "
            "/run/user/1000/zellij/contract_version_1/main",
        ]
    )
    with (
        patch(
            "ztc.sessions.services.zellij_session.shutil.which", return_value="/usr/bin/pgrep"
        ),
        patch(
            "ztc.sessions.services.zellij_session.subprocess.run",
            return_value=_mock_pgrep(pgrep_output),
        ),
    ):
        result = get_attached_session_clients()
    assert result == {"main": 2}


def test_only_servers_yields_empty_dict() -> None:
    """Server vivo sin clientes attacheados = sesion detached."""
    pgrep_output = _make_pgrep_output(
        [
            "100 /home/martin/.local/bin/zellij --server "
            "/run/user/1000/zellij/contract_version_1/orphan",
        ]
    )
    with (
        patch(
            "ztc.sessions.services.zellij_session.shutil.which", return_value="/usr/bin/pgrep"
        ),
        patch(
            "ztc.sessions.services.zellij_session.subprocess.run",
            return_value=_mock_pgrep(pgrep_output),
        ),
    ):
        result = get_attached_session_clients()
    assert result == {}


def test_unknown_argv_format_skipped_silently() -> None:
    """Cliente que zsm no creo (sin -s/--session/attach), no se cuenta."""
    pgrep_output = _make_pgrep_output(
        [
            "100 /home/martin/.local/bin/zellij",  # sin args, no se sabe sesion
            "200 /home/martin/.local/bin/zellij attach main",
        ]
    )
    with (
        patch(
            "ztc.sessions.services.zellij_session.shutil.which", return_value="/usr/bin/pgrep"
        ),
        patch(
            "ztc.sessions.services.zellij_session.subprocess.run",
            return_value=_mock_pgrep(pgrep_output),
        ),
    ):
        result = get_attached_session_clients()
    # Solo el segundo cliente se contó.
    assert result == {"main": 1}


def test_excludes_lookalike_binaries() -> None:
    """`myzellij`, `zellij-fork`, etc. no son `zellij`."""
    pgrep_output = _make_pgrep_output(
        [
            "100 /usr/bin/myzellij attach fake",
            "200 /usr/bin/zellij-wrapper -s nope",
            "300 /home/martin/.local/bin/zellij attach real",
        ]
    )
    with (
        patch(
            "ztc.sessions.services.zellij_session.shutil.which", return_value="/usr/bin/pgrep"
        ),
        patch(
            "ztc.sessions.services.zellij_session.subprocess.run",
            return_value=_mock_pgrep(pgrep_output),
        ),
    ):
        result = get_attached_session_clients()
    assert result == {"real": 1}


def test_returns_none_when_pgrep_not_available() -> None:
    """Sin pgrep -> caller debe saber que no se pudo determinar."""
    with patch(
        "ztc.sessions.services.zellij_session.shutil.which", return_value=None
    ):
        result = get_attached_session_clients()
    assert result is None


def test_returns_none_on_pgrep_timeout() -> None:
    """Timeout de pgrep -> tampoco se pudo determinar."""
    import subprocess as sp

    with (
        patch(
            "ztc.sessions.services.zellij_session.shutil.which", return_value="/usr/bin/pgrep"
        ),
        patch(
            "ztc.sessions.services.zellij_session.subprocess.run",
            side_effect=sp.TimeoutExpired(cmd="pgrep", timeout=2.0),
        ),
    ):
        result = get_attached_session_clients()
    assert result is None


# ---------- list_sessions integra deteccion de attached/detached ----------


def _mock_zellij_list_output(stdout: str):
    class _Result:
        def __init__(self, out: str) -> None:
            self.stdout = out
            self.stderr = ""
            self.returncode = 0

    return _Result(stdout)


def test_list_sessions_marks_attached_when_client_present() -> None:
    list_output = "main [Created 1h ago]\n"
    pgrep_output = _make_pgrep_output(
        ["100 /usr/bin/zellij attach main"]
    )

    def fake_run(argv, **kwargs):
        if argv[0] == "pgrep":
            return _mock_pgrep(pgrep_output)
        return _mock_zellij_list_output(list_output)

    def fake_which(name):
        # Both zellij and pgrep available.
        return f"/usr/bin/{name}"

    with (
        patch("ztc.sessions.services.zellij_session.shutil.which", side_effect=fake_which),
        patch("ztc.sessions.services.zellij_session.subprocess.run", side_effect=fake_run),
    ):
        sessions = list_sessions()
    assert len(sessions) == 1
    assert sessions[0].name == "main"
    assert sessions[0].state == "attached"
    assert sessions[0].attached_clients == 1


def test_list_sessions_marks_detached_when_no_client() -> None:
    list_output = "main [Created 1h ago]\n"
    pgrep_output = _make_pgrep_output([])  # ningun cliente, ningun server

    def fake_run(argv, **kwargs):
        if argv[0] == "pgrep":
            return _mock_pgrep(pgrep_output)
        return _mock_zellij_list_output(list_output)

    def fake_which(name):
        return f"/usr/bin/{name}"

    with (
        patch("ztc.sessions.services.zellij_session.shutil.which", side_effect=fake_which),
        patch("ztc.sessions.services.zellij_session.subprocess.run", side_effect=fake_run),
    ):
        sessions = list_sessions()
    assert len(sessions) == 1
    assert sessions[0].state == "detached"
    assert sessions[0].attached_clients == 0


def test_list_sessions_falls_back_to_running_when_pgrep_unavailable() -> None:
    """Si pgrep no esta, las running quedan como running (no attached/detached)."""
    list_output = "main [Created 1h ago]\n"

    def fake_which(name):
        if name == "pgrep":
            return None
        return f"/usr/bin/{name}"

    with (
        patch("ztc.sessions.services.zellij_session.shutil.which", side_effect=fake_which),
        patch(
            "ztc.sessions.services.zellij_session.subprocess.run",
            return_value=_mock_zellij_list_output(list_output),
        ),
    ):
        sessions = list_sessions()
    assert len(sessions) == 1
    assert sessions[0].state == "running"


def test_list_sessions_keeps_exited_state_independent_of_clients() -> None:
    """exited no se ve afectado por la deteccion de clientes."""
    list_output = "old [Created 2d ago] (EXITED - attach to resurrect)\n"
    pgrep_output = _make_pgrep_output(
        ["100 /usr/bin/zellij attach old"]
    )

    def fake_run(argv, **kwargs):
        if argv[0] == "pgrep":
            return _mock_pgrep(pgrep_output)
        return _mock_zellij_list_output(list_output)

    def fake_which(name):
        return f"/usr/bin/{name}"

    with (
        patch("ztc.sessions.services.zellij_session.shutil.which", side_effect=fake_which),
        patch("ztc.sessions.services.zellij_session.subprocess.run", side_effect=fake_run),
    ):
        sessions = list_sessions()
    assert len(sessions) == 1
    assert sessions[0].state == "exited"
