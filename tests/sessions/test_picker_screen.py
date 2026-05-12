from __future__ import annotations

from ztc.sessions.models.session import SessionState, ZellijSession
from ztc.sessions.screens.picker import PickerScreen
from ztc.sessions.services.session_info import PaneInfo, TabInfo


def _session(name: str, state: SessionState) -> ZellijSession:
    return ZellijSession(name=name, state=state)


def test_destructive_block_reasons_by_state() -> None:
    exited = _session("old", "exited")
    attached = _session("live", "attached")
    detached = _session("away", "detached")
    running = _session("run", "running")
    unknown = _session("mystery", "unknown")

    assert "already exited" in (
        PickerScreen._destructive_block_reason(exited, "kill") or ""
    )
    assert PickerScreen._destructive_block_reason(attached, "kill") is None
    assert PickerScreen._destructive_block_reason(detached, "kill") is None
    assert PickerScreen._destructive_block_reason(running, "kill") is None
    assert "unknown" in (
        PickerScreen._destructive_block_reason(unknown, "kill") or ""
    )

    assert PickerScreen._destructive_block_reason(exited, "delete") is None
    assert "without force" in (
        PickerScreen._destructive_block_reason(attached, "delete") or ""
    )

    assert PickerScreen._destructive_block_reason(exited, "delete-force") is None
    assert PickerScreen._destructive_block_reason(attached, "delete-force") is None
    assert "unknown" in (
        PickerScreen._destructive_block_reason(unknown, "delete-force") or ""
    )


def test_detail_tree_renderer_keeps_tabs_and_panes_separate() -> None:
    screen = PickerScreen()
    tree = screen._render_tabs_tree(
        [
            TabInfo(
                name="main",
                panes=[PaneInfo(command="bash", cwd="/tmp", size="60%")],
            )
        ]
    )

    assert "main" in tree
    assert "bash" in tree
    assert "────────" not in tree


def test_footer_hotkeys_are_split_by_launch_and_manage_actions() -> None:
    screen = PickerScreen()

    launch = screen._launch_keys_label()
    manage = screen._manage_keys_label()

    assert launch.index("New") < launch.index("Layout") < launch.index("Bash")
    assert PickerScreen(embedded=True)._back_keys_label().endswith("Back")
    assert "Exit" in PickerScreen(embedded=False)._back_keys_label()
    assert (
        manage.index("Reload")
        < manage.index("Rename")
        < manage.index("Kill")
        < manage.index("Delete")
        < manage.index("--force")
    )
    assert screen._palette_keys_label().endswith("Palette")
