from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual.screen import ModalScreen

from ztc.services.terminals import TerminalBackend
from ztc.services.terminals.kitty import (
    KittyBackend,
    is_listen_on_set,
    is_remote_control_disabled,
    read_listen_on,
    read_remote_control,
    read_ztc_pref,
    write_listen_on_default,
    write_remote_control_yes,
    write_ztc_pref,
)
from ztc.widgets.confirm import KittyRemoteControlChoice, KittyRemoteControlModal


@dataclass(frozen=True)
class StartupCheck:
    modal: ModalScreen[Any]
    on_result: Callable[[Any], None]


def build_startup_check(
    backend: TerminalBackend,
    backend_path: Path,
    app: Any,
) -> StartupCheck | None:
    builder = STARTUP_CHECKS.get(backend.kind)
    if builder is None:
        return None
    return builder(backend, backend_path, app)


def build_kitty_remote_control_check(
    backend: TerminalBackend,
    backend_path: Path,
    app: Any,
) -> StartupCheck | None:
    if not isinstance(backend, KittyBackend):
        return None
    doc = backend.load(backend_path)
    if read_ztc_pref(doc, "remote_control_modal") == "dismissed":
        return None

    remote_control = read_remote_control(doc)
    if remote_control == "password":
        return None
    remote_disabled = is_remote_control_disabled(remote_control)
    listen_missing = not is_listen_on_set(read_listen_on(doc))
    if not remote_disabled and not listen_missing:
        return None

    def on_result(choice: KittyRemoteControlChoice | None) -> None:
        if choice is None:
            return
        current_doc = backend.load(backend_path)
        if choice.action == "enable":
            added = 0
            if is_remote_control_disabled(read_remote_control(current_doc)):
                write_remote_control_yes(current_doc)
                added += 1
            if not is_listen_on_set(read_listen_on(current_doc)):
                write_listen_on_default(current_doc)
                added += 1
            try:
                backend.save(current_doc, backend_path)
            except Exception as exc:  # noqa: BLE001
                app.notify(
                    f"Error updating Kitty config: {exc}",
                    severity="error",
                    timeout=8,
                )
                return
            app.notify(
                f"Added {added} line(s) to kitty.conf. "
                "Restart Kitty for auto-reload to take effect.",
                severity="information",
                timeout=8,
            )
            return

        if choice.dont_show_again:
            write_ztc_pref(current_doc, "remote_control_modal", "dismissed")
            try:
                backend.save(current_doc, backend_path)
            except Exception as exc:  # noqa: BLE001
                app.notify(
                    f"Error updating Kitty config: {exc}",
                    severity="error",
                    timeout=8,
                )
                return
            app.notify(
                "Kitty auto-reload prompt disabled.",
                severity="information",
                timeout=6,
            )

    return StartupCheck(
        modal=KittyRemoteControlModal(),
        on_result=on_result,
    )


STARTUP_CHECKS: dict[
    str,
    Callable[[TerminalBackend, Path, Any], StartupCheck | None],
] = {
    "kitty": build_kitty_remote_control_check,
}
