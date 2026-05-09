# Plan: launcher refactor + bug fixes for v1.0.0

This is the plan for the **single commit** that closes v1.0.0 with all
known issues addressed. Once this lands and the user verifies it, we
tag `v1.0.0` and create the GitHub Release.

## Context

Two issues were discovered during v1.0.0 polish that must be fixed
before the release tag:

1. **Terminal lock when exiting Zellij** (severe). Launching a Zellij
   session from inside `ztc` (via the embedded "Zellij sessions"
   menu) leaves the terminal unresponsive after exiting Zellij with
   `Ctrl+Q`. Reproducible in any host terminal (Alacritty, Kitty,
   gnome-terminal). Running `zsm` standalone from the shell does
   not have this bug — only the embedded path is affected.

2. **`default_bg` not detected in sessions detail** (cosmetic). The
   sessions detail view shows colored swatches per pane, but for
   hand-written layouts (where `default_bg` is a child node, not a
   property), the parser returns `None` and the swatch falls back to
   neutral gray.

A first round of patching these fixes already exists in the working
tree (uncommitted). This plan **finalizes** the work via a clean
refactor that removes duplicated dispatch logic, eliminates the
in-progress "stepping stone" code, and keeps everything testable.

## Root cause of issue #1

Two entry points launch Zellij from a TUI:

- `zsm` standalone — `src/ztc/sessions/__main__.py`
- `ztc` embedded — `src/ztc/app.py:_handle_session_launch`

The standalone path does the right thing:

```python
app.run()                  # blocks; on exit Textual restores cooked mode + leaves alt-screen
target = app.target
os.execvp(zellij, …)       # only AFTER terminal is restored
```

The embedded path called `os.execvp` from inside the Textual event
loop, while the terminal was still in raw mode + alt-screen. Zellij
inherited that state. When Zellij exits, it restores the state it
found — leaving the host terminal unusable.

## Solution overview

1. Make the embedded path **defer** the `execvp` until after
   `app.run()` returns, mirroring the standalone path.
2. Extract the dispatch logic (`target → argv → execvp`) into a
   single shared function so both entry points are trivial wrappers.
3. Tighten the `LaunchTarget` type from a free-form `str` action to
   `Literal["attach", "new", "bash"]` so typos and unhandled cases
   are caught statically. Keep a runtime `sys.exit` guard in the
   dispatch as defense-in-depth (matching what `zsm` does today).
4. Fix the unrelated `session_info.py` parsing bug (small, isolated)
   **with a regression test** so it cannot decay silently again
   (it slipped in the first place because no test covered
   `default_bg` parsing).

## What lives in the working tree right now (to be cleaned up)

These are the in-progress patches I made before deciding on the
refactor. They are functional but partially duplicate logic that the
refactor centralizes. The refactor must **remove** them, not leave
them in place.

| File | Current "patch" code | Action in refactor |
|---|---|---|
| `src/ztc/__main__.py` | `_dispatch_pending(target)` local function with the if/elif/elif dispatch | **Remove**. Replace `main()` body with `launcher.dispatch_target(app.pending_launch)`. |
| `src/ztc/__main__.py` | Imports of `os`, `attach_argv`, `new_session_argv`, `LaunchTarget` | **Remove**. Only `TermConfigApp` and `launcher` are needed. |
| `tests/test_app_menu_gating.py` | 4 tests named `test_dispatch_pending_*` | **Move** to `tests/sessions/test_launcher.py`, renamed to `test_dispatch_target_*` (function rename). |

What stays from the in-progress patches:

| File | Code that stays | Why |
|---|---|---|
| `src/ztc/app.py` | `self.pending_launch` attribute + `_handle_session_launch` setting it and calling `self.exit()` | This is the **correct** ztc-side contract — handler must not call execvp from the event loop. |
| `src/ztc/app.py` | Removal of `import os` and the launcher imports | Already cleaned. Keep clean. |
| `src/ztc/sessions/services/session_info.py` | `_read_default_bg` helper + its usage in `_collect_layout_panes` | Bug #2 fix. Orthogonal to launcher refactor. |
| `tests/test_app_menu_gating.py` | 3 tests named `test_sessions_launch_*_sets_pending` | They verify the ztc-side contract: handler stores target on the app, does not invoke `execvp`. |

## Final file layout

### New file

`src/ztc/sessions/launcher.py` (~30 lines):

```python
"""Translates a LaunchTarget into the corresponding os.execvp call.

The helper exists so both entry points (standalone `zsm` and embedded
`ztc`) share a single dispatch implementation. It must NOT be called
from inside a Textual event loop — by construction it is invoked
*after* `app.run()` returns, when the terminal is back in cooked
mode and the alt-screen has been left."""

from __future__ import annotations

import os
import sys

from ztc.sessions.services.zellij_session import attach_argv, new_session_argv
from ztc.sessions.types import LaunchTarget


def dispatch_target(target: LaunchTarget) -> None:
    if target is None:
        return
    action, payload, extra = target
    if action == "attach":
        argv = attach_argv(payload or "")
        os.execvp(argv[0], argv)
    elif action == "new":
        argv = new_session_argv(payload or "", layout=extra)
        os.execvp(argv[0], argv)
    elif action == "bash":
        shell = os.environ.get("SHELL") or "/bin/bash"
        os.execvp(shell, [shell])
    else:
        # Defense-in-depth. With LaunchTarget tightened to a Literal
        # action, the type checker should already reject any other
        # value at construction time. This branch only triggers if
        # someone bypasses typing (e.g., dynamic data, untyped tests).
        sys.exit(f"unknown action: {action}")
```

The companion change to `src/ztc/sessions/types.py`:

```python
from typing import Literal

# (action, payload, layout). action is one of "attach" | "new" | "bash".
# None means the user dismissed without choosing.
LaunchAction = Literal["attach", "new", "bash"]
LaunchTarget = tuple[LaunchAction, str | None, str | None] | None
```

### Updated entry points

`src/ztc/__main__.py`:

```python
from ztc.app import TermConfigApp
from ztc.sessions import launcher


def main() -> None:
    app = TermConfigApp()
    app.run()
    launcher.dispatch_target(app.pending_launch)


if __name__ == "__main__":
    main()
```

`src/ztc/sessions/__main__.py`:

```python
from ztc.sessions.app import SessionLauncherApp
from ztc.sessions import launcher


def main() -> None:
    app = SessionLauncherApp()
    app.run()
    launcher.dispatch_target(app.target)


if __name__ == "__main__":
    main()
```

Both entry points become 5 lines of substance.

### Unchanged

- `src/ztc/app.py` — keeps `pending_launch` and the handler that sets
  it and calls `self.exit()`. No further changes.
- `src/ztc/sessions/app.py` — no changes (already had `app.target`).
- `src/ztc/sessions/services/session_info.py` — keeps the
  `_read_default_bg` helper (bug #2 fix). No further changes.
- `pyproject.toml` — version stays at `1.0.0`. We do **not** bump to
  `1.0.1` — see versioning section below.

## Test reorganization

### `tests/sessions/test_launcher.py` (new file)

Holds the dispatch-level tests. 5 tests, all using `monkeypatch` on
`ztc.sessions.launcher.os.execvp`:

- `test_dispatch_target_attach_invokes_execvp` — asserts
  `("attach", session, _)` → `execvp("zellij", […, "attach", session])`.
- `test_dispatch_target_new_invokes_execvp` — same for `("new", …)`.
- `test_dispatch_target_bash_invokes_execvp` — same for `("bash", …)`.
- `test_dispatch_target_none_is_noop` — `None` target makes no call.
- `test_dispatch_target_unknown_action_exits` — passes a target with
  an action like `"frobnicate"` (bypassing the type system via
  `cast` or `# type: ignore`) and asserts that `dispatch_target`
  raises `SystemExit` with a message mentioning the bad action.

Each test is sync (no `async`) since `dispatch_target` is sync.

### `tests/sessions/test_session_info.py` (additions)

Two new tests covering `default_bg` parsing — these did not exist
before, which is exactly why bug #2 went unnoticed. They live next
to the rest of `session_info.py` coverage.

- `test_default_bg_property_form` — fixture KDL with
  `pane default_bg="#aabbcc"`. Asserts `PaneInfo.default_bg ==
  "#aabbcc"`. Regression check on the form already supported.
- `test_default_bg_child_node_form` — fixture KDL with
  `pane { default_bg "#aabbcc" }`. Asserts the same. This is the
  bug #2 regression test.

### `tests/test_app_menu_gating.py` (changes)

- Keep the 3 tests `test_sessions_launch_attach_sets_pending`,
  `test_sessions_launch_new_sets_pending`,
  `test_sessions_launch_bash_sets_pending`. They verify the ztc app's
  contract: the handler sets `pending_launch` and does not invoke
  `execvp` from the event loop.
- `test_picker_blocks_launch_when_zellij_not_installed` is **already
  broken** in the working tree because it does
  `monkeypatch.setattr("ztc.app.os.execvp", …)` and `ztc.app` no
  longer imports `os`. Rewrite: drop the `monkeypatch.setattr` and
  the `captured` assertions; instead, assert
  `app.pending_launch is None` after each blocked action and
  `app.pending_launch == ("bash", None, None)` after `action_bash`.
- The `test_sessions_launch_none_target_is_noop` test stays — just
  asserts that handler called with `None` keeps `pending_launch` as
  `None`.
- Remove the 4 `test_dispatch_pending_*` tests I added (they move to
  the new file).

## Versioning strategy

- `pyproject.toml` stays at `1.0.0`.
- We do **not** create a `v1.0.1` release.
- After this commit and after the user verifies the fix, we tag
  `v1.0.0` on this commit (not on the previous `bc69d21`).
- GitHub Release `v1.0.0` = first stable release with all fixes
  baked in. The history of `main` shows the polishing commits, but
  the public release record starts clean.

## Order of operations

1. **Roll back the test changes** I made in
   `tests/test_app_menu_gating.py` so the file matches `main`
   (revert just the 5 modified/added test bodies). This avoids
   keeping a partially-correct test file in the working tree while
   the refactor is in progress.
2. Tighten `LaunchTarget` in `src/ztc/sessions/types.py` to use
   `Literal["attach", "new", "bash"]`. Run `uv run ruff check` for
   lint hygiene — note that ruff is **not** a type checker and will
   not validate that callers respect the `Literal`. Behavioral
   guarantees come from the test suite and the `else: sys.exit(...)`
   guard in `dispatch_target`. (mypy/pyright would close the loop
   statically but are not configured in this project today.)
3. Create `src/ztc/sessions/launcher.py` with `dispatch_target`,
   including the `else: sys.exit(...)` guard.
4. Simplify `src/ztc/__main__.py` to use `launcher.dispatch_target`.
   Drop `_dispatch_pending` and unused imports.
5. Simplify `src/ztc/sessions/__main__.py` to use
   `launcher.dispatch_target`. Drop the inline if/elif and unused
   imports.
6. Recreate the dispatch tests in `tests/sessions/test_launcher.py`
   (5 tests including the unknown-action one).
7. Add the two `default_bg` parsing tests in
   `tests/sessions/test_session_info.py`.
8. Re-add the `*_sets_pending` tests in `tests/test_app_menu_gating.py`
   (rewriting the originals to assert the new contract). Rewrite
   `test_picker_blocks_launch_when_zellij_not_installed` to assert
   `pending_launch` instead of patching `ztc.app.os.execvp`.
9. Run `uv run pytest -q`. All green.
10. Single commit: refactor + bug fixes + tests + cleanup.

## Acceptance criteria

- `uv run pytest -q` passes (no regressions; all new and updated
  tests green).
- `rg -n "_dispatch_pending" src/ztc/` returns **zero** matches
  (in code or tests — the function name does not survive).
- `rg -n "os\.execvp\(" src/ztc/` returns **exactly one** call
  site, inside `src/ztc/sessions/launcher.py`. The pattern uses
  `\(` so docstrings/comments mentioning the term in prose are
  excluded — the check counts actual calls.
- `rg -n "^import os" src/ztc/__main__.py src/ztc/sessions/__main__.py
  src/ztc/app.py` returns no matches in the two `__main__.py` files
  and no matches in `app.py` either (they no longer touch `os`).
- Manual smoke test by user: open `ztc` from a terminal, navigate
  to **Zellij sessions**, attach to a session or create new with
  layout, exit Zellij with `Ctrl+Q`, verify the host terminal is
  responsive and you can keep typing.
- Sessions detail correctly shows colored swatches for panes that
  declare `default_bg` as a child node (e.g. user's
  `~/.config/zellij/layouts/dev.kdl`).
- Both new `test_default_bg_*` tests in
  `tests/sessions/test_session_info.py` pass — verified before the
  commit, not just claimed.

## Out of scope for this commit

- Changing the launcher to *return* to `ztc` after Zellij exits
  (instead of replacing the process). That requires moving from
  `os.execvp` to `subprocess.Popen` + waitpid, which is a significant
  redesign. The user mentioned this would be desirable but agreed
  it is a separate concern. Ticket for v1.1.0 if pursued.
- The `default_bg` editable feature in the layout editor — covered
  by `PLAN_PANE_DEFAULT_BG.md` (separate plan, separate commit).

## Risk and rollback

- **Low risk**. The refactor is mechanical: same code, moved.
- The only behavior change is: `ztc`-embedded launching now defers
  `execvp` until after `app.run()` returns. That is the bug fix.
- **Rollback**: `git revert` the commit. The terminal lock returns
  but the rest of the app keeps working.
