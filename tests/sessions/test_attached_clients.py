"""Tests del detector de clientes attached.

`get_attached_session_clients` lista los PIDs de `zellij` con
`pgrep -x zellij` y lee el argv de cada uno desde `/proc/<pid>/cmdline`
(NUL-separated). Los tests mockean `subprocess.run` (pgrep), `_proc_cmdline`
(el argv simulado de cada PID) y `_build_inode_session_map` (la deteccion
por socket). Si Zellij cambia como un cliente identifica su sesion en
argv, estos tests rompen y nos enteramos.
"""

from __future__ import annotations

from unittest.mock import patch

from ztc.sessions.services.zellij_session import (
    _parse_ss_unix_lines,
    _session_name_from_argv,
    get_attached_session_clients,
    list_sessions,
)

_MOD = "ztc.sessions.services.zellij_session"


class _Result:
    """Stub minimo de `subprocess.CompletedProcess`."""

    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def _pids_text(pids: list[int]) -> str:
    return "".join(f"{p}\n" for p in pids)


# ---------- _session_name_from_argv (parser puro) ----------


def test_argv_attach_name() -> None:
    assert _session_name_from_argv(["zellij", "attach", "main"]) == "main"


def test_argv_attach_alias() -> None:
    assert _session_name_from_argv(["zellij", "a", "main"]) == "main"


def test_argv_dash_s() -> None:
    assert _session_name_from_argv(["zellij", "-s", "main2"]) == "main2"


def test_argv_dash_s_joined() -> None:
    assert _session_name_from_argv(["zellij", "-smain2"]) == "main2"


def test_argv_long_session() -> None:
    assert _session_name_from_argv(["zellij", "--session", "work"]) == "work"


def test_argv_long_session_equals() -> None:
    assert _session_name_from_argv(["zellij", "--session=work"]) == "work"


def test_argv_with_layout() -> None:
    assert (
        _session_name_from_argv(["zellij", "-n", "compact", "-s", "main"])
        == "main"
    )


def test_argv_attach_skips_flags() -> None:
    assert (
        _session_name_from_argv(["zellij", "attach", "--create", "fresh"])
        == "fresh"
    )


def test_argv_name_with_spaces_attach() -> None:
    assert (
        _session_name_from_argv(["zellij", "attach", "commodore 3"])
        == "commodore 3"
    )


def test_argv_name_with_spaces_dash_s() -> None:
    assert (
        _session_name_from_argv(["zellij", "-s", "my session"]) == "my session"
    )


def test_argv_returns_none_when_no_match() -> None:
    """`zellij` solo, sin args reconocibles -> no podemos saber sesion."""
    assert _session_name_from_argv(["zellij"]) is None


def test_argv_returns_none_for_options_subcommand() -> None:
    """`zellij options ...` es un subcommand sin sesion."""
    assert _session_name_from_argv(["zellij", "options", "--help"]) is None


# ---------- _parse_ss_unix_lines (parser de `ss -xa`) ----------


def test_parse_ss_maps_peer_inode_to_session() -> None:
    text = (
        "u_str ESTAB 0 0 "
        "/run/user/1000/zellij/contract_version_1/main 111 * 222\n"
    )
    assert _parse_ss_unix_lines(text) == {222: "main"}


def test_parse_ss_session_name_with_spaces() -> None:
    text = (
        "u_str ESTAB 0 0 "
        "/run/user/1000/zellij/contract_version_1/commodore 3 111 * 222\n"
    )
    assert _parse_ss_unix_lines(text) == {222: "commodore 3"}


def test_parse_ss_ignores_non_estab_and_non_zellij() -> None:
    text = (
        "u_str LISTEN 0 128 "
        "/run/user/1000/zellij/contract_version_1/main 111 * 0\n"
        "u_str ESTAB 0 0 /run/user/1000/something/else 333 * 444\n"
    )
    assert _parse_ss_unix_lines(text) == {}


# ---------- get_attached_session_clients (pgrep + /proc/<pid>/cmdline) ----------


def test_clients_counted_per_session() -> None:
    cmdlines = {
        808405: [
            "/home/martin/.local/bin/zellij",
            "--server",
            "/run/user/1000/zellij/contract_version_1/main",
        ],
        808500: ["/home/martin/.local/bin/zellij", "attach", "main"],
        808600: ["/home/martin/.local/bin/zellij", "-s", "work"],
    }
    with (
        patch(f"{_MOD}.shutil.which", return_value="/usr/bin/pgrep"),
        patch(
            f"{_MOD}.subprocess.run",
            return_value=_Result(_pids_text(list(cmdlines))),
        ),
        patch(f"{_MOD}._build_inode_session_map", return_value={}),
        patch(f"{_MOD}._proc_cmdline", side_effect=cmdlines.get),
    ):
        result = get_attached_session_clients()
    assert result == {"main": 1, "work": 1}


def test_multiple_clients_for_same_session() -> None:
    """Dos terminales attacheadas a la misma sesion = count 2."""
    cmdlines = {
        100: ["/usr/bin/zellij", "attach", "main"],
        200: ["/usr/bin/zellij", "attach", "main"],
        300: [
            "/usr/bin/zellij",
            "--server",
            "/run/user/1000/zellij/contract_version_1/main",
        ],
    }
    with (
        patch(f"{_MOD}.shutil.which", return_value="/usr/bin/pgrep"),
        patch(
            f"{_MOD}.subprocess.run",
            return_value=_Result(_pids_text(list(cmdlines))),
        ),
        patch(f"{_MOD}._build_inode_session_map", return_value={}),
        patch(f"{_MOD}._proc_cmdline", side_effect=cmdlines.get),
    ):
        result = get_attached_session_clients()
    assert result == {"main": 2}


def test_session_name_with_spaces_counted() -> None:
    cmdlines = {100: ["/usr/bin/zellij", "attach", "commodore 3"]}
    with (
        patch(f"{_MOD}.shutil.which", return_value="/usr/bin/pgrep"),
        patch(
            f"{_MOD}.subprocess.run",
            return_value=_Result(_pids_text(list(cmdlines))),
        ),
        patch(f"{_MOD}._build_inode_session_map", return_value={}),
        patch(f"{_MOD}._proc_cmdline", side_effect=cmdlines.get),
    ):
        result = get_attached_session_clients()
    assert result == {"commodore 3": 1}


def test_only_servers_yields_empty_dict() -> None:
    """Server vivo sin clientes attacheados = sesion detached."""
    cmdlines = {
        100: [
            "/usr/bin/zellij",
            "--server",
            "/run/user/1000/zellij/contract_version_1/orphan",
        ],
    }
    with (
        patch(f"{_MOD}.shutil.which", return_value="/usr/bin/pgrep"),
        patch(
            f"{_MOD}.subprocess.run",
            return_value=_Result(_pids_text(list(cmdlines))),
        ),
        patch(f"{_MOD}._build_inode_session_map", return_value={}),
        patch(f"{_MOD}._proc_cmdline", side_effect=cmdlines.get),
    ):
        result = get_attached_session_clients()
    assert result == {}


def test_unknown_argv_format_skipped_silently() -> None:
    """Cliente sin -s/--session/attach en argv -> no se cuenta."""
    cmdlines = {
        100: ["/usr/bin/zellij"],  # sin args, no se sabe sesion
        200: ["/usr/bin/zellij", "attach", "main"],
    }
    with (
        patch(f"{_MOD}.shutil.which", return_value="/usr/bin/pgrep"),
        patch(
            f"{_MOD}.subprocess.run",
            return_value=_Result(_pids_text(list(cmdlines))),
        ),
        patch(f"{_MOD}._build_inode_session_map", return_value={}),
        patch(f"{_MOD}._proc_cmdline", side_effect=cmdlines.get),
    ):
        result = get_attached_session_clients()
    assert result == {"main": 1}


def test_excludes_lookalike_binaries() -> None:
    """`myzellij`, `zellij-wrapper`, etc. no son `zellij`."""
    cmdlines = {
        100: ["/usr/bin/myzellij", "attach", "fake"],
        200: ["/usr/bin/zellij-wrapper", "-s", "nope"],
        300: ["/home/martin/.local/bin/zellij", "attach", "real"],
    }
    with (
        patch(f"{_MOD}.shutil.which", return_value="/usr/bin/pgrep"),
        patch(
            f"{_MOD}.subprocess.run",
            return_value=_Result(_pids_text(list(cmdlines))),
        ),
        patch(f"{_MOD}._build_inode_session_map", return_value={}),
        patch(f"{_MOD}._proc_cmdline", side_effect=cmdlines.get),
    ):
        result = get_attached_session_clients()
    assert result == {"real": 1}


def test_unreadable_cmdline_skipped() -> None:
    """PID cuyo /proc/<pid>/cmdline no se puede leer (proceso terminado)."""
    cmdlines = {200: ["/usr/bin/zellij", "attach", "main"]}
    with (
        patch(f"{_MOD}.shutil.which", return_value="/usr/bin/pgrep"),
        patch(
            f"{_MOD}.subprocess.run",
            return_value=_Result(_pids_text([100, 200])),
        ),
        patch(f"{_MOD}._build_inode_session_map", return_value={}),
        patch(f"{_MOD}._proc_cmdline", side_effect=cmdlines.get),
    ):
        result = get_attached_session_clients()
    assert result == {"main": 1}


def test_socket_detection_takes_priority_over_argv() -> None:
    """Si el socket map resuelve la sesion, gana sobre lo que diga el argv."""
    cmdlines = {100: ["/usr/bin/zellij", "attach", "argv-name"]}
    with (
        patch(f"{_MOD}.shutil.which", return_value="/usr/bin/pgrep"),
        patch(
            f"{_MOD}.subprocess.run",
            return_value=_Result(_pids_text(list(cmdlines))),
        ),
        patch(f"{_MOD}._build_inode_session_map", return_value={42: "ignored"}),
        patch(f"{_MOD}._proc_cmdline", side_effect=cmdlines.get),
        patch(
            f"{_MOD}._session_via_sockets",
            side_effect=lambda pid, m: "socket-name",
        ),
    ):
        result = get_attached_session_clients()
    assert result == {"socket-name": 1}


def test_returns_none_when_pgrep_not_available() -> None:
    """Sin pgrep -> caller debe saber que no se pudo determinar."""
    with patch(f"{_MOD}.shutil.which", return_value=None):
        result = get_attached_session_clients()
    assert result is None


def test_returns_none_on_pgrep_timeout() -> None:
    """Timeout de pgrep -> tampoco se pudo determinar."""
    import subprocess as sp

    with (
        patch(f"{_MOD}.shutil.which", return_value="/usr/bin/pgrep"),
        patch(
            f"{_MOD}.subprocess.run",
            side_effect=sp.TimeoutExpired(cmd="pgrep", timeout=2.0),
        ),
    ):
        result = get_attached_session_clients()
    assert result is None


# ---------- list_sessions integra deteccion de attached/detached ----------


def _list_run(list_output: str, pgrep_pids: list[int]):
    """side_effect para subprocess.run: zellij list-sessions vs pgrep."""

    def fake_run(argv, **kwargs):
        if argv[0] == "pgrep":
            return _Result(_pids_text(pgrep_pids))
        return _Result(list_output)

    return fake_run


def test_list_sessions_marks_attached_when_client_present() -> None:
    with (
        patch(f"{_MOD}.shutil.which", side_effect=lambda n: f"/usr/bin/{n}"),
        patch(
            f"{_MOD}.subprocess.run",
            side_effect=_list_run("main [Created 1h ago]\n", [100]),
        ),
        patch(f"{_MOD}._build_inode_session_map", return_value={}),
        patch(
            f"{_MOD}._proc_cmdline",
            side_effect={100: ["/usr/bin/zellij", "attach", "main"]}.get,
        ),
    ):
        sessions = list_sessions()
    assert len(sessions) == 1
    assert sessions[0].name == "main"
    assert sessions[0].state == "attached"
    assert sessions[0].attached_clients == 1


def test_list_sessions_marks_detached_when_no_client() -> None:
    with (
        patch(f"{_MOD}.shutil.which", side_effect=lambda n: f"/usr/bin/{n}"),
        patch(
            f"{_MOD}.subprocess.run",
            side_effect=_list_run("main [Created 1h ago]\n", []),
        ),
        patch(f"{_MOD}._build_inode_session_map", return_value={}),
        patch(f"{_MOD}._proc_cmdline", side_effect=lambda pid: None),
    ):
        sessions = list_sessions()
    assert len(sessions) == 1
    assert sessions[0].state == "detached"
    assert sessions[0].attached_clients == 0


def test_list_sessions_falls_back_to_running_when_pgrep_unavailable() -> None:
    """Si pgrep no esta, las running quedan como running."""

    def fake_which(name):
        return None if name == "pgrep" else f"/usr/bin/{name}"

    with (
        patch(f"{_MOD}.shutil.which", side_effect=fake_which),
        patch(
            f"{_MOD}.subprocess.run",
            return_value=_Result("main [Created 1h ago]\n"),
        ),
    ):
        sessions = list_sessions()
    assert len(sessions) == 1
    assert sessions[0].state == "running"


def test_list_sessions_keeps_exited_state_independent_of_clients() -> None:
    """exited no se ve afectado por la deteccion de clientes."""
    with (
        patch(f"{_MOD}.shutil.which", side_effect=lambda n: f"/usr/bin/{n}"),
        patch(
            f"{_MOD}.subprocess.run",
            side_effect=_list_run(
                "old [Created 2d ago] (EXITED - attach to resurrect)\n", [100]
            ),
        ),
        patch(f"{_MOD}._build_inode_session_map", return_value={}),
        patch(
            f"{_MOD}._proc_cmdline",
            side_effect={100: ["/usr/bin/zellij", "attach", "old"]}.get,
        ),
    ):
        sessions = list_sessions()
    assert len(sessions) == 1
    assert sessions[0].state == "exited"
