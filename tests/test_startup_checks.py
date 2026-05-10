from __future__ import annotations

from pathlib import Path

from ztc.services.terminals.kitty import KittyBackend
from ztc.startup_checks import StartupCheck, build_startup_check
from ztc.widgets.confirm import KittyRemoteControlChoice, KittyRemoteControlModal


class _App:
    def __init__(self) -> None:
        self.notifications: list[tuple[str, str | None]] = []

    def notify(
        self,
        message: str,
        *,
        severity: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.notifications.append((message, severity))


def _kitty_path(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "kitty.conf"
    path.write_text(text, encoding="utf-8")
    return path


def test_build_startup_check_returns_none_when_already_reachable(
    tmp_path: Path,
) -> None:
    path = _kitty_path(
        tmp_path,
        "allow_remote_control yes\nlisten_on unix:@ztc-{kitty_pid}\n",
    )
    assert build_startup_check(KittyBackend(), path, _App()) is None


def test_build_startup_check_returns_none_for_password_choice(
    tmp_path: Path,
) -> None:
    path = _kitty_path(tmp_path, "allow_remote_control password\n")
    assert build_startup_check(KittyBackend(), path, _App()) is None


def test_build_startup_check_returns_none_when_dismissed(
    tmp_path: Path,
) -> None:
    path = _kitty_path(
        tmp_path,
        '# ztc:{"remote_control_modal": "dismissed"}\n'
        "allow_remote_control yes\n",
    )
    assert build_startup_check(KittyBackend(), path, _App()) is None


def test_build_startup_check_returns_modal_when_missing_directives(
    tmp_path: Path,
) -> None:
    path = _kitty_path(tmp_path, "")
    check = build_startup_check(KittyBackend(), path, _App())
    assert isinstance(check, StartupCheck)
    assert isinstance(check.modal, KittyRemoteControlModal)


def test_enable_adds_only_missing_directives(tmp_path: Path) -> None:
    path = _kitty_path(tmp_path, "allow_remote_control yes\n")
    app = _App()
    check = build_startup_check(KittyBackend(), path, app)
    assert check is not None
    check.on_result(KittyRemoteControlChoice(action="enable"))
    text = path.read_text(encoding="utf-8")
    assert "allow_remote_control yes\n" in text
    assert text.count("allow_remote_control yes") == 1
    assert "listen_on unix:@ztc-{kitty_pid}" in text
    assert app.notifications == [
        (
            "Added 1 line(s) to kitty.conf. "
            "Restart Kitty for auto-reload to take effect.",
            "information",
        )
    ]


def test_enable_adds_both_directives_when_both_missing(tmp_path: Path) -> None:
    path = _kitty_path(tmp_path, "")
    app = _App()
    check = build_startup_check(KittyBackend(), path, app)
    assert check is not None
    check.on_result(KittyRemoteControlChoice(action="enable"))
    assert path.read_text(encoding="utf-8").splitlines() == [
        "allow_remote_control yes",
        "listen_on unix:@ztc-{kitty_pid}",
    ]
    assert app.notifications[0][0].startswith("Added 2 line(s)")


def test_skip_with_remember_writes_dismissal_pref(tmp_path: Path) -> None:
    path = _kitty_path(tmp_path, "font_size 12.0\n")
    check = build_startup_check(KittyBackend(), path, _App())
    assert check is not None
    check.on_result(
        KittyRemoteControlChoice(action="skip", dont_show_again=True)
    )
    assert path.read_text(encoding="utf-8").splitlines() == [
        "font_size 12.0",
        '# ztc:{"remote_control_modal": "dismissed"}',
    ]


def test_skip_without_remember_and_dismiss_write_nothing(tmp_path: Path) -> None:
    path = _kitty_path(tmp_path, "")
    check = build_startup_check(KittyBackend(), path, _App())
    assert check is not None
    check.on_result(KittyRemoteControlChoice(action="skip"))
    check.on_result(None)
    assert path.read_text(encoding="utf-8") == ""
