from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual.screen import ModalScreen

from ztc.services.terminals import TerminalBackend
from ztc.services.terminals.kitty import (
    KittyBackend,
    is_dynamic_background_opacity_enabled,
    is_listen_on_set,
    is_remote_control_disabled,
    read_dynamic_background_opacity,
    read_listen_on,
    read_remote_control,
    read_ztc_pref,
    write_dynamic_background_opacity_yes,
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
    manifest_path: Path,
    app: Any,
) -> StartupCheck | None:
    builder = STARTUP_CHECKS.get(backend.kind)
    if builder is None:
        return None
    return builder(backend, manifest_path, app)


def build_kitty_remote_control_check(
    backend: TerminalBackend,
    manifest_path: Path,
    app: Any,
) -> StartupCheck | None:
    # `manifest_path` es el archivo default (= manifest cuando hay perfiles,
    # o config standalone cuando aun no se convirtio). Las managed directives
    # (`allow_remote_control`, `listen_on`, `dynamic_background_opacity`) y
    # las prefs `# ztc:` viven aca: son globales a la instancia Kitty, no
    # por perfil — si vivieran en el perfil, switchear de perfil romperia
    # el remote control y deshabilitaria los reloads IPC.
    if not isinstance(backend, KittyBackend):
        return None
    doc = backend.load(manifest_path)
    if read_ztc_pref(doc, "remote_control_modal") == "dismissed":
        return None

    remote_control = read_remote_control(doc)
    inside_zellij = _is_inside_zellij()
    remote_disabled = is_remote_control_disabled(remote_control)
    listen_missing = inside_zellij and not is_listen_on_set(read_listen_on(doc))
    dynamic_opacity_missing = not is_dynamic_background_opacity_enabled(
        read_dynamic_background_opacity(doc)
    )
    if not remote_disabled and not listen_missing and not dynamic_opacity_missing:
        return None

    def on_result(choice: KittyRemoteControlChoice | None) -> None:
        if choice is None:
            return
        current_doc = backend.load(manifest_path)
        if choice.action == "enable":
            added = 0
            if is_remote_control_disabled(read_remote_control(current_doc)):
                write_remote_control_yes(current_doc)
                added += 1
            if inside_zellij and not is_listen_on_set(read_listen_on(current_doc)):
                write_listen_on_default(current_doc)
                added += 1
            if not is_dynamic_background_opacity_enabled(
                read_dynamic_background_opacity(current_doc)
            ):
                write_dynamic_background_opacity_yes(current_doc)
                added += 1
            if added:
                pending_instance = _current_kitty_instance_marker()
                if pending_instance is not None:
                    write_ztc_pref(
                        current_doc,
                        "remote_control_pending_instance",
                        pending_instance,
                    )
            try:
                backend.save(current_doc, manifest_path)
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
                backend.save(current_doc, manifest_path)
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
        modal=KittyRemoteControlModal(
            inside_zellij=inside_zellij,
            remote_control_missing=remote_disabled,
            listen_on_missing=listen_missing,
            dynamic_background_opacity_missing=dynamic_opacity_missing,
        ),
        on_result=on_result,
    )


def _is_inside_zellij() -> bool:
    return bool(os.environ.get("ZELLIJ") or os.environ.get("ZELLIJ_SESSION_NAME"))


def _current_kitty_instance_marker() -> str | None:
    if pid := os.environ.get("KITTY_PID"):
        return f"pid:{pid}"
    if window_id := os.environ.get("KITTY_WINDOW_ID"):
        return f"window:{window_id}"
    return None


STARTUP_CHECKS: dict[
    str,
    Callable[[TerminalBackend, Path, Any], StartupCheck | None],
] = {
    "kitty": build_kitty_remote_control_check,
}
