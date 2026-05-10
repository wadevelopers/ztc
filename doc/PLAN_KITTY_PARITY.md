# Plan: Kitty parity — import + auto-reload

Target version: **v1.2.0**. Two stages:

- **Stage A** (✅ done in commit `f363beb`): theme + settings import
  reach feature parity with Alacritty.
- **Stage B** (next): saving from ZTC actually applies in Kitty —
  socket-based auto-reload via
  `kitty @ --to "$KITTY_LISTEN_ON" load-config` with educational
  modal explaining the `allow_remote_control` + `listen_on`
  setup. **Redesigned after smoke test 7**: TTY-based
  `kitty @ load-config` (without `--to`) fails inside Zellij
  ("Error: i/o timeout") because Zellij intermediates the pty;
  the socket path with `--to` succeeds because `KITTY_LISTEN_ON`
  propagates as env var through Zellij. Phases 4 and 5 of
  smoke test 7 validated the new design before re-implementing.

## Context

`ColorEditorScreen.action_import` and
`TerminalSettingsScreen.action_import` are the two import flows the
app exposes today. Both currently exit early with a "not supported"
toast when the active backend is Kitty:

```python
if not isinstance(self.backend, AlacrittyBackend):
    self.app.notify(f"... not supported on {self.backend.display_name}.", ...)
    return
```

Only Alacritty has the import capability wired. This is historical,
not a technical limitation — Kitty's parser, slot reader/writer and
settings reader/writer all already exist; what is missing is the
`import_theme_file` method on `KittyBackend` and the removal of the
two `isinstance` guards.

The file picker plan (`PLAN_FILE_PICKER.md`, target v1.3.0)
modernizes both import flows to use a `FilePickerModal` instead of
the current `PromptModal`. The picker plan now sits in v1.3.0 because
v1.2.0 expanded to cover Kitty's auto-reload story (Stage B below)
— a more coherent theme for one release.

## Stage A scope (already done)

Strict feature parity with Alacritty's existing import:

- **Theme import** in the color editor: copy color slots from a
  source Kitty `.conf` file into the current Kitty config.
- **Settings import** in the terminal settings screen: copy
  `padding x/y`, `opacity`, `font.family`, `font.size`,
  `cursor.shape` from a source `.conf` into the current config.
  This flow is already protocol-based (uses `load`,
  `read_setting`, `write_setting`) and works for any backend
  that implements the protocol — only the `isinstance` guard
  blocks Kitty today.

Out of scope: cross-backend import (importing from `.toml` into a
Kitty config or vice versa). The format mismatch is non-trivial; if
that capability is wanted later, it's its own design problem.

## Stage A files (already implemented)

| # | Path | Change |
|---|---|---|
| 1 | `src/ztc/services/terminals/__init__.py` | Add `import_theme_file(doc: BackendDoc, source_path: Path) -> int` to the `TerminalBackend` Protocol. Doc: "copies color slots from another config of the same backend; returns count of slots overwritten; raises `FileNotFoundError` if `source_path` does not exist". This lets the color editor call `self.backend.import_theme_file(...)` without an `isinstance` narrowing. |
| 2 | `src/ztc/services/terminals/kitty.py` | Add `KittyBackend.import_theme_file(doc, source_path) -> int`. Body mirrors `AlacrittyBackend.import_theme_file` literally: raise `FileNotFoundError` if `source_path` does not exist; open via `self.load`; iterate `KNOWN_SLOTS` (Kitty's own list at line 84); for each slot read the source value with `self.read_slot`; **skip if `value is None or not is_valid_hex(value)`** (matches Alacritty's filter — `normalize_hex` would error on invalid input); on valid, write via `self.write_slot(doc, slot, normalize_hex(value))`; count overwrites; return. |
| 3 | `src/ztc/services/terminals/alacritty.py` | No logic change. Existing `import_theme_file` already matches the new protocol signature; just verify during implementation. |
| 4 | `src/ztc/screens/color_editor.py` | Remove the `if not isinstance(self.backend, AlacrittyBackend)` guard in `action_import` (~line 257). The remaining body works as-is because it uses protocol methods. Update the comment "Capability solo de Alacritty: import desde otro alacritty.toml" to reflect the new reality. |
| 5 | `src/ztc/screens/terminal_settings.py` | Remove the equivalent guard in `action_import` (~line 270-275). The body is already protocol-based; no further change. Update the comment "Capability solo de Alacritty: import de settings desde otro alacritty.toml" likewise. |
| 6 | `tests/test_terminal_kitty.py` | Add unit tests for `KittyBackend.import_theme_file`: imports from a fixture `.conf`, asserts color slots are copied; missing source raises `FileNotFoundError`; invalid hex values are skipped. |
| 7 | `tests/test_color_editor_screen.py` (currently empty) | Add an integration test: open color editor with a Kitty backend, **first** monkey-patch `app.push_screen` to capture the second arg (the `after` callback), **then** call `screen.action_import()`. The callback is captured during that call; afterwards invoke it directly with a fixture `.conf` path. Assert no "not supported" toast (i.e. the action does not exit early before `push_screen`), and that `screen.dirty` is `True` and the doc has the imported slots. The modal itself is not exercised — that's Stage B's responsibility. |
| 8 | `tests/test_terminal_settings_screen.py` | Add an equivalent integration test for the settings import path with Kitty backend, using the same monkey-patch-before-action-import pattern. |

## Stage A design decisions

- **Promote `import_theme_file` to the Protocol**, instead of leaving
  it as an Alacritty-only capability accessed via `isinstance`
  narrowing. Reason: the operation is conceptually backend-agnostic
  (read color slots from another config of the same backend, copy
  into the current), and Kitty's implementation is structurally
  identical. Promoting to the protocol makes the call site simpler
  and is the natural shape for any future third backend
  (Ghostty/WezTerm/etc.).

- **Same-backend import only** (no cross-backend). A Kitty source
  imports into Kitty; an Alacritty source imports into Alacritty.
  Cross-backend would require translating between `.toml` and
  `.conf` formats and resolving format mismatches, which is a
  separate design problem outside this plan's scope.

- **Mirror error handling**: `FileNotFoundError` if the source
  doesn't exist; load errors propagate from `self.load`. The
  caller (the screens) already handle these and show toast
  notifications.

- **Preserve `KNOWN_SLOTS` per-backend**. Each backend defines
  its own `KNOWN_SLOTS: list[CanonicalSlot]` reflecting which slots
  it supports. Kitty's at line 84 of `kitty.py`; Alacritty's at
  line 38 of `alacritty.py`. The new `KittyBackend.import_theme_file`
  uses Kitty's list. No consolidation in this plan.

## Stage A out of scope

- Cross-backend import (Alacritty source into Kitty, etc.).
- File picker integration — that's `PLAN_FILE_PICKER.md` (target
  v1.3.0). Stage A keeps the existing `PromptModal` for both backends;
  the picker plan replaces it for both at once when v1.3.0 lands.
- Adding new categories of import (e.g., importing layouts or themes
  by name) that don't exist for Alacritty either.
- Refactoring the existing Alacritty implementation. Changes there
  are limited to verifying the protocol signature.

## Stage A acceptance criteria (verified at `f363beb`)

- `uv run pytest -q` passes including the new tests.
- `uv run ruff check` clean.
- `rg -n "isinstance\(.*AlacrittyBackend\)" src/ztc/screens/` returns
  zero matches in `color_editor.py` and `terminal_settings.py`
  (`action_import` paths) — the two guards are gone.
- Manual smoke test: with Kitty as the active backend, open the
  color editor, press `i` for import, type a path to a `.conf` file
  with color directives, confirm — colors land in the active
  config; save persists them. No "not supported" toast.
- Manual smoke test: same with terminal settings (e.g., padding,
  font from a source `.conf`).
- Alacritty paths continue working (no regression).

## Versioning

- Stage A is **already committed** (`f363beb`).
- Stage B (auto-reload, detailed below) closes v1.2.0 with a single
  commit at the end.
- Per project rules, the `1.2.0` bump in `pyproject.toml` and the
  `v1.2.0` tag happen after Stage B is committed and the user
  verifies. The push to GitHub + GitHub Release are explicit
  user-triggered actions, not part of the execution flow.

---

# Stage B — Kitty auto-reload

Saving config changes from ZTC currently writes to `kitty.conf`
correctly, but Kitty does not auto-reload its config. The user has
to press `Ctrl+Shift+F5` manually (or restart Kitty) for changes
to render. This stage adds an auto-reload path with an educational
modal that explains the trade-off.

## Stage B context

Three pieces interact:

1. **`allow_remote_control` in kitty.conf**: Kitty's config option
   that enables remote control. Default is `no`. **Read at startup
   only** — changing it requires restarting Kitty.
2. **`listen_on` in kitty.conf**: tells Kitty to expose remote
   control via a Unix socket and exports the socket path as the
   `KITTY_LISTEN_ON` env var into shells launched by Kitty. Required
   (in addition to `allow_remote_control` permissive) for
   `kitty @ --to <socket>` to work from inside terminal multiplexers
   like Zellij. Without `listen_on`, only the controlling-TTY path
   is available, and that path is broken in Zellij (smoke test 7
   phase 2 confirmed: "Error: i/o timeout").
3. **`kitty @ load-config`**: Kitty's CLI to apply a config reload.
   Without `--to` it talks to the controlling TTY of the calling
   process. Inside Zellij, that TTY is Zellij's pty, not Kitty's —
   the command times out. With `--to "$KITTY_LISTEN_ON"` it bypasses
   the TTY and connects directly to Kitty's listening socket.
   **`KITTY_LISTEN_ON` propagates through Zellij** (smoke test 7
   phase 4: same value inside and outside Zellij), so the socket
   path is the working solution for the realistic deployment (most
   ZTC users run inside Zellij).

For inside-Zellij auto-reload, both directives are needed:
`allow_remote_control` permissive AND `listen_on` set. Either one
missing means `KITTY_LISTEN_ON` is unset (or the listener never
started), and the reload either falls through to the broken TTY
path or fails entirely.

Stage B implements:

- A **hybrid save**: after writing to disk, ZTC reads
  `os.environ.get("KITTY_LISTEN_ON")`; if set, runs
  `kitty @ --to "$KITTY_LISTEN_ON" load-config`; otherwise runs
  plain `kitty @ load-config` (works only outside Zellij). On
  success the standard "Saved: <file>" toast is shown without
  manual-reload hint. On failure (remote control disabled,
  `listen_on` not configured, Kitty not running, advanced auth
  modes), the toast appends "Press Ctrl+Shift+F5 in Kitty to
  reload."
- An **educational modal** at startup, shown only when:
  - The active backend is Kitty, AND
  - The current config makes auto-reload unreachable from inside
    Zellij (i.e. `allow_remote_control` is `no`/absent, OR
    `listen_on` is absent — and the user does not have the
    deliberate-choice value `password`), AND
  - The dismissal preference is not set
  The modal explains the trade-off and offers: enable now (ZTC
  appends whichever of the two directives are missing to
  kitty.conf and asks the user to restart Kitty) or skip (with
  optional "don't show again" checkbox).
- A **dismissal preference** stored as a comment line in
  `kitty.conf`: `# ztc:{"remote_control_modal":"dismissed"}`.
  Format chosen for: zero new files, parseable with `json.loads`
  out of the box, identifiable via a strict prefix
  (`^# ztc:`), self-healing (if the user accidentally deletes the
  line, the next ZTC run treats it as never-asked and shows the
  modal again — which is benign).

## Stage B state machine

`allow_remote_control` accepts: `yes`, `no`, `password`, `socket`,
`socket-only`. `listen_on` accepts a socket address (the default
ZTC writes is `unix:@ztc-{kitty_pid}`, where `{kitty_pid}` is
Kitty's canonical PID placeholder) or is absent.

The educational modal exists for **one specific user-flow gap**: a
user has auto-reload objectively unavailable from inside Zellij —
either remote control is disabled, or `listen_on` is unset — and
probably doesn't realize that's why ZTC's saves don't auto-apply.

Two predicates encode the modal trigger:

- `is_remote_control_disabled(value: str | None) -> bool`: True
  for `"no"` and `None`. Other values (`yes`, `socket`,
  `socket-only`) need additional check on `listen_on`. `password`
  is treated as deliberate user choice — never modify.
- `is_listen_on_set(value: str | None) -> bool`: True only when
  `value` has real socket content. False for `None`, empty string,
  whitespace-only, and the literal `"none"` (Kitty's
  default-disabled sentinel — `listen_on none` means "no listener"
  even though the directive is present). Signature mirrors
  `is_remote_control_disabled(value)` so callers use a uniform
  shape: `read_*` extracts, predicate evaluates.

State machine:

| `allow_remote_control` | `listen_on` | Dismissal comment | Modal? | Enable adds |
|---|---|---|---|---|
| `password` | (any) | (any) | No | — (deliberate choice) |
| `yes`/`socket`/`socket-only` | set | (any) | No | — (already reachable) |
| `yes`/`socket`/`socket-only` | absent | dismissed | No | — |
| `yes`/`socket`/`socket-only` | absent | not present | Yes | `listen_on` only |
| `no`/absent | set | dismissed | No | — |
| `no`/absent | set | not present | Yes | `allow_remote_control yes` only |
| `no`/absent | absent | dismissed | No | — |
| `no`/absent | absent | not present | Yes | both directives |

The save flow is **independent of these predicates**. It always
attempts `kitty @ --to "$KITTY_LISTEN_ON" load-config` (or the
plain form when env var unset); success or failure is determined
by `subprocess.run`'s actual outcome. The fallback notice handles
every failure mode uniformly (disabled, listen_on missing,
password without credentials, Kitty not running, etc.).

`read_remote_control(doc) -> str | None` and `read_listen_on(doc)
-> str | None` return raw values (or `None` when absent),
preserving information for any future logic.

Modal results:

- **"Enable" clicked**: ZTC computes which directive(s) are
  missing per the table above and appends only those to
  `kitty.conf`. Toast: "Added N line(s) to kitty.conf. Restart
  Kitty for auto-reload to take effect." No `# ztc:` comment is
  written — next startup sees the directives and skips the modal
  naturally.
- **"Skip" clicked, checkbox checked**: ZTC writes
  `# ztc:{"remote_control_modal":"dismissed"}` to kitty.conf. Next
  startup respects it.
- **"Skip" clicked, checkbox NOT checked**: ZTC writes nothing.
  Modal will appear again next startup.

## Stage B files

| # | Path | Change |
|---|---|---|
| 1 | `src/ztc/services/terminals/__init__.py` (Protocol) | Add two backend-runtime methods, keeping the Protocol free of Textual/UI objects. (a) `reload_after_save(self) -> bool` — "Try to apply the most recent saved config to the running terminal. Returns True on success or when the backend auto-reloads natively (no action needed). Returns False when the backend cannot reload programmatically — caller falls back to the manual hint." (b) `manual_reload_hint(self) -> str \| None` — "User-facing instruction string shown when `reload_after_save()` returns False. Returns None if the backend never needs a manual hint (e.g. Alacritty: auto-reload native)." Update the `TerminalBackend` class docstring so it mentions both theme/settings I/O and post-save reload/hint behavior. Choice rationale: `reload_after_save` is a backend capability, and `manual_reload_hint` is backend-owned data consumed by `save_helper`; neither requires importing Textual or constructing UI from the backend. **Do not add `startup_check()` or `StartupCheck` to this Protocol**: startup modals are UI/app orchestration, not terminal config I/O. |
| 2 | `src/ztc/services/terminals/alacritty.py` | Add two minimal implementations: `reload_after_save(self) -> bool: return True` (Alacritty watches its own config file natively); `manual_reload_hint(self) -> str \| None: return None` (no action ever required). No startup/UI method in the backend. |
| 3 | `src/ztc/services/terminals/kitty.py` | Add Kitty's backend-runtime method implementations and pure config helpers only. `manual_reload_hint(self) -> str: return "Press Ctrl+Shift+F5 in Kitty to reload."`. (a) Helpers for `allow_remote_control`: `read_remote_control(doc) -> str \| None` returns the **effective** value. Because these helpers live at module level, they call `_linearize(doc.path, doc.lines, in_main=True)` directly rather than instantiating `KittyBackend` just to call `_effective_entries`; this is the same effective-read path used by slot reads and honors included files. `is_remote_control_disabled(value: str \| None) -> bool` returns True only for `"no"` and None; every other value (`yes`/`password`/`socket`/`socket-only`) is treated as a deliberate user choice. `write_remote_control_yes(doc)` appends `allow_remote_control yes` to the main config. (b) Helpers for `listen_on` (mirror the same shape): `read_listen_on(doc) -> str \| None` returns the effective value via direct `_linearize(...)`. `is_listen_on_set(value: str \| None) -> bool` returns True only when `value` has real socket content; False for `None`, empty string, whitespace-only, and the literal `"none"` (Kitty's disabled-sentinel — `listen_on none` is a valid line that means "no listener"). **Case-sensitive comparison against `"none"`** (lowercase) — matches Kitty's documented sentinel exactly; non-canonical variants like `"None"`/`"NONE"` are treated as opaque socket names and the empirical reload outcome decides if they work (no defensive normalization without verifying Kitty's parser). Signature takes `value` (not `doc`) to mirror `is_remote_control_disabled`; callers use the uniform shape `read_*` then predicate. `write_listen_on_default(doc)` appends `listen_on unix:@ztc-{kitty_pid}` to the main config. `{kitty_pid}` is Kitty's canonical placeholder syntax (single braces, lowercase) — Kitty substitutes it per-instance, yielding unique sockets per Kitty process. The `ztc-` prefix namespaces the socket so it doesn't collide with sockets the user may have configured for other purposes. The resulting `KITTY_LISTEN_ON` value is opaque to ZTC and passed verbatim to `--to`. (c) `read_ztc_pref(doc, key)` and `write_ztc_pref(doc, key, value)` helpers manage a strict-prefix `# ztc:` JSON line in `kitty.conf`. Use private helpers as needed (`_parse_ztc_line`, `_ztc_line_indices`, `_read_ztc_dict`) to keep the public helpers small. **Read**: scan all lines, parse every line matching `^# ztc:` as a JSON **object**; malformed JSON and valid non-object JSON (`# ztc:[...]`, `# ztc:42`, etc.) are ignored. Merge parsed objects into a single dict with last-wins per key (so multiple lines from manual edits get reconciled). Return `dict.get(key)`. **Write**: read merged dict, set `dict[key] = value`, then **delete every existing `# ztc:` line and append a single canonical line** at the end (`# ztc:` + `json.dumps(dict, sort_keys=True)`). The prefix is ZTC's namespace — dedupe is safe (no risk of clobbering unrelated user comments). Result: file always has at most one `# ztc:` line after a write. (d) `reload_after_save(self) -> bool`: dual-attempt loop. Reads `os.environ.get("KITTY_LISTEN_ON")` once. For each binary in `(kitty, kitten)`: builds `[binary, @]`, appends `--to <env_value>` if env var set, appends `load-config`, runs `subprocess.run(cmd, timeout=2, capture_output=True)`; returns True on first `returncode == 0`. Catches `Exception` broadly (FileNotFoundError, TimeoutExpired, etc.) — reload is opportunistic, no error must ever propagate to make a successful save look failed. Returns False if both attempts fail. The `--to` path is the working solution for inside-Zellij deployment (smoke test 7 phase 5: OK); the plain form is preserved for users outside Zellij who have only `allow_remote_control yes` without `listen_on`. |
| 4 | `src/ztc/widgets/confirm.py` | New `KittyRemoteControlModal(ModalScreen[KittyRemoteControlChoice \| None])` with: educational text mentioning that auto-reload from inside Zellij requires both `allow_remote_control` permissive AND `listen_on` set (and that ZTC will add only what's missing on Enable), `[Enable]` and `[Skip]` buttons, and a "Don't show this again" checkbox. **Result type is a `@dataclass(frozen=True) class KittyRemoteControlChoice` with `action: Literal["enable", "skip"]` and `dont_show_again: bool = False`** (defined in the same file alongside the modal). Dataclass over tuple: callsites read `choice.action` / `choice.dont_show_again` instead of `choice[0]` / `choice[1]`, and the field name documents semantics that a positional tuple loses. The "Enable" button always returns `dont_show_again=False` (the checkbox is irrelevant in that branch since the directives in `kitty.conf` are themselves the signal that suppresses the modal next startup). `None` is returned only on Esc-dismiss. **Initial focus on `Skip`** — accidental Enter must not modify `kitty.conf`; mirrors the `UnsavedChangesModal` precedent (focus on Cancel). Style consistent with other modals in the file. |
| 5 | `src/ztc/services/save_helper.py` (new) | (a) `save_with_reload(backend, doc, path) -> SaveResult` encapsulates the save+reload sequence: invoke `backend.save(doc, path)` (captures backup path), invoke `backend.reload_after_save()` (captures bool), and **when `reload_ok=False`, queries `backend.manual_reload_hint()`** to populate the hint. Returns a dataclass with **only data**: `backup_path: Path \| None`, `reload_ok: bool`, `manual_reload_hint: str \| None` (set when `reload_ok=False` and the backend provides a hint). Errors from `backend.save` propagate. (b) `compose_save_toast(file_name: str, result: SaveResult) -> str` composes the toast format used by the two save screens: "Saved: <file_name>" + optional "(backup: <name>)" + optional "\\n<hint>" when reload failed. **Not used by theme_sync** — that caller has its own message format ("Kitty updated: N slot(s)") and composes its own toast using the same `result` data. **No per-backend mapping inside `save_helper`**: the hint comes from the Protocol method, so adding Ghostty later requires zero edits here. |
| 6 | `src/ztc/startup_checks.py` (new) + `src/ztc/app.py` | Add a UI/app-layer startup-check registry keyed by `backend.kind`, keeping Textual modal orchestration out of terminal backends while avoiding an `isinstance` ladder in `app.py`. New dataclass: `StartupCheck(modal: ModalScreen[Any], on_result: Callable[[Any], None])`. New helper: `build_startup_check(backend, backend_path, app) -> StartupCheck \| None`, internally dispatching via `STARTUP_CHECKS: dict[str, Callable[..., StartupCheck \| None]]`. Implement the `"kitty"` entry here: load `kitty.conf`, evaluate the state machine using pure helpers from `ztc.services.terminals.kitty`, and return `StartupCheck(modal=KittyRemoteControlModal(), on_result=<closure>)` when the modal should appear. The closure receives `KittyRemoteControlChoice \| None` and handles Enable / Skip+remember / Skip / dismiss: append directives via `write_remote_control_yes`/`write_listen_on_default`, or write the `# ztc:` pref via `write_ztc_pref`, then `backend.save(...)` and `app.notify(...)`. In `TermConfigApp.on_mount`, after backend detection and normal startup setup: `check = build_startup_check(self.backend, self.backend_path, self)` when both backend/path exist; if non-None, `self.push_screen(check.modal, check.on_result)`. Result: `app.py` has one generic hook, `kitty.py` remains config/backend logic only, and a future backend adds one registry entry plus a UI helper instead of changing backend Protocol shape. |
| 7 | `src/ztc/screens/color_editor.py` (`action_save`) | Call `save_with_reload(self.backend, self.doc, self.backend_path)`. On success notify `compose_save_toast(self.backend_path.name, result)`. On exception (from `backend.save` re-raised) notify the error. The screen no longer references `reload_after_save` or `manual_reload_hint`. |
| 8 | `src/ztc/screens/terminal_settings.py` (`action_save`) | Same change as #7. |
| 9 | `src/ztc/services/theme_sync.py` (`sync_terminal_with_zellij_theme`) | Replace the direct `backend.save(...)` call with `save_with_reload(backend, doc, backend_path)`. **Wire the existing `SyncResult.backup` from `result.backup_path`** — preserves current behavior. **Extend `SyncResult`** with `reload_ok: bool = True` and `manual_reload_hint: str \| None = None` (defaults chosen so early returns — file inexistente, theme without colors, "no changes" — are treated as "no reload was attempted, nothing failed"; consumers checking `reload_ok=False` only ever see it when an actual save+reload cycle ran and the reload failed). When a save actually happens, populate from `SaveResult`: `sync_result.reload_ok = save_result.reload_ok`, `sync_result.manual_reload_hint = save_result.manual_reload_hint`. Service stays purely data-returning, no message composition. |
| 9b | `src/ztc/screens/theme_editor.py` (already composes toast from `SyncResult`) | Extend toast composition to append `\\n<manual_reload_hint>` when `reload_ok=False`. Pure additive change. |
| 9c | `src/ztc/screens/custom_theme_editor.py` (today **discards** `SyncResult`) | **Behavior change**: capture the result of `sync_terminal_with_zellij_theme(...)`. On `reload_ok=False`, show a toast containing the manual hint (so the user knows to Ctrl+Shift+F5). On `reload_ok=True`, stay silent — preserves the current quiet UX of the success case. Exceptions still notify error as before. |
| 10 | `tests/test_terminal_kitty.py` | Tests for `read_remote_control` (each value: yes/no/password/socket/socket-only/absent, including values coming from an included file), `is_remote_control_disabled` (truth table — True only for `"no"` and None), `write_remote_control_yes`, `read_listen_on` (set/absent/`none`-literal, including values coming from an included file), `is_listen_on_set` truth table (`None` → False, `""` → False, `"   "` → False, `"none"` → False, `"None"` → True (case-sensitive: opaque socket name), `"unix:@ztc-1234"` → True, `"unix:/tmp/sock"` → True), `write_listen_on_default` (line written matches `listen_on unix:@ztc-{kitty_pid}`), `read_ztc_pref`/`write_ztc_pref`: round-trip, missing line, malformed JSON ignored, valid non-object JSON ignored, multiple keys in same line, **multiple `# ztc:` lines in file → read merges last-wins; write collapses to single canonical line at end of file**, write preserves non-`# ztc:` content unchanged. `reload_after_save` (mock `subprocess.run` and `os.environ`): with `KITTY_LISTEN_ON` set → command list includes `["--to", <value>]`; without → plain command; kitty success returns True; kitty fails + kitten success returns True; both fail returns False; FileNotFoundError; TimeoutExpired. |
| 11 | `tests/test_widgets_confirm.py` (new file or extend existing) | Tests for `KittyRemoteControlModal`: Enable button → `KittyRemoteControlChoice(action="enable", dont_show_again=False)` regardless of checkbox state; Skip + checkbox unchecked → `KittyRemoteControlChoice(action="skip", dont_show_again=False)`; Skip + checkbox checked → `KittyRemoteControlChoice(action="skip", dont_show_again=True)`; Esc → `None`; initial focus is on the Skip button. |
| 12 | `tests/test_startup_checks.py` (new) + `tests/test_app_menu_gating.py` | Two layers of tests, mirroring the responsibility split: (a) **In `tests/test_startup_checks.py`**: `build_startup_check(kitty_backend, kitty_path, stub_app)` returns the right `StartupCheck` (or `None`) for each row of the state machine table; the `on_result` callback, invoked with each `KittyRemoteControlChoice` value, writes the right directives / `# ztc:` pref and notifies the right toast. Use a stub app that records `notify` calls. (b) **In `test_app_menu_gating.py`**: `app.py` invokes `build_startup_check(...)` during startup and pushes the returned modal — monkey-patch `ztc.app.build_startup_check` to return a sentinel `StartupCheck`, no Kitty knowledge in the app test. Also test that when backend/path are missing (SSH/unsupported), no startup check is requested. |
| 13 | `tests/test_color_editor_screen.py` | One simple save-flow test: monkey-patch `save_with_reload` to return a known `SaveResult`, assert the screen calls `compose_save_toast` correctly and notifies the result. The actual toast-content assertions live in `test_save_helper.py`. |
| 14 | `tests/test_terminal_settings_screen.py` | Same as #13. |
| 15 | `tests/test_theme_sync.py` (new file or extend existing) | Tests scoped to the **service** layer only: `sync_terminal_with_zellij_theme` returns `SyncResult` with correct `backup`, `reload_ok`, and `manual_reload_hint` populated from the underlying `save_with_reload`. Mocks `save_with_reload`. **Does not test toast composition** — that's the responsibility of `test_theme_picker_screen.py` / `test_custom_theme_editor_screen.py`, which assert the screens correctly compose toasts (or stay silent in custom_theme_editor's success case) given mocked `SyncResult` values. |
| 16 | `tests/test_save_helper.py` (new) | Unit tests for `save_with_reload` and `compose_save_toast`: alacritty success (backup + auto-reload), kitty success (backup + reload_ok), kitty fallback (backup + reload failed → toast includes hint), save error propagates. Centralizes the toast-content assertions. |

> Note on Protocol surface: this plan adds **two** methods to
> `TerminalBackend`: `reload_after_save()` and `manual_reload_hint()`.
> `manual_reload_hint` lives in the Protocol instead of a `dict[str, str]`
> inside `save_helper.py`, because the hint is backend-owned data and
> future backends should not require edits to `save_helper.py`.
> Startup modals are different: they are UI/app orchestration, not
> terminal config I/O. The startup modal dispatch therefore lives in
> `ztc.startup_checks` as a registry keyed by `backend.kind`, keeping
> `app.py` generic without forcing terminal backend modules to import
> Textual widgets or construct modals.

## Stage B design decisions

- **Separate `reload_after_save()` method, do not change `save()`'s
  contract.** `save()` is `(doc, path) -> Path | None` (returns the
  backup path or None). Both screens use that return value as the
  backup. Adding reload-success to `save()` would force changing
  every caller and rewriting tests for nothing — the operations
  are conceptually distinct (write to disk vs ask the running app
  to apply it). Cleaner: a new Protocol method that returns a
  single bool. Alacritty's default returns `True` (auto-reload;
  treat as success). Kitty's tries `kitty @ load-config`.

- **Modal predicate is "is auto-reload reachable from inside
  Zellij?", with `password` as deliberate-choice exception**. Two
  config bits matter: `allow_remote_control` permissive AND
  `listen_on` set. If both are present, auto-reload works. If
  either is missing, it doesn't (in the realistic Zellij
  deployment). The predicate triggers the modal when the
  combination is broken and the user hasn't dismissed. `password`
  is the one value that suppresses the modal regardless of
  `listen_on` state — it signals deliberate auth setup that ZTC
  must not silently rewrite. The save flow is **independent of
  this predicate**: it always attempts the reload; success or
  failure is determined by `subprocess.run`'s actual outcome, not
  by guessing from config values. The fallback notice handles every
  failure mode uniformly (disabled, listen_on missing, password
  without credentials, kitty not running, etc.). Raw values are
  preserved by `read_remote_control()` and `read_listen_on()` for
  any future logic that wants to distinguish modes.

- **Socket-based reload, with TTY fallback for non-Zellij users**.
  Smoke test 7 confirmed empirically: phase 2
  (`kitty @ load-config` plain, inside Zellij) fails with "Error:
  i/o timeout" because the controlling TTY of the subprocess is
  Zellij's pty rather than Kitty's. Phase 5
  (`kitty @ --to "$KITTY_LISTEN_ON" load-config`, inside Zellij)
  succeeds because `--to` bypasses TTY routing. Phase 4 confirmed
  `KITTY_LISTEN_ON` propagates identically inside and outside
  Zellij. Therefore `reload_after_save` reads
  `os.environ.get("KITTY_LISTEN_ON")`; if set, prepends
  `--to <value>` to the command (works both inside and outside
  Zellij); if unset, falls back to plain `kitty @` (works only
  outside Zellij, for users with `allow_remote_control yes` and
  no `listen_on`). The dual-attempt loop applies the same logic to
  the `kitten @` alias.

- **Modal "Enable" path adds whichever directives are missing**.
  For inside-Zellij deployment, both `allow_remote_control yes`
  AND `listen_on unix:@ztc-{kitty_pid}` are required. Computing
  the missing set per-call (rather than always writing both)
  preserves minimal-edit principle: a user who already has one
  directive set gets only the other appended, not a duplicate
  line. `{kitty_pid}` is Kitty's canonical placeholder syntax —
  Kitty substitutes the actual PID at runtime per-instance,
  producing unique sockets per Kitty process. The `ztc-` prefix
  namespaces the socket so it doesn't collide with sockets the
  user configured for other tools.

- **Dual-attempt: `kitty @` first, then `kitten @`**. Verified
  locally with Kitty 0.32.2: both commands work and accept `--to`.
  Older Kitty (pre-0.27 approximately) had only `kitty @`. Future
  Kitty: unknown. We try `kitty @` first (historically universal),
  fall back to `kitten @` (newer alias) on any failure. The same
  `--to <socket>` arg is applied to both (no version-specific
  branching). Costs at most one extra `subprocess.run` (2s
  timeout) when both fail.

- **Hybrid over pure-auto**. ZTC always tries the reload command
  (with `--to` when env var is set, plain otherwise) but never
  assumes it'll work. The fallback notice is the safety net for
  users who skipped the modal, whose Kitty was started before
  configuring `listen_on`, or who use
  `allow_remote_control password`.

- **No `# ztc:` comment when user enables**. The fact that
  `allow_remote_control yes` (and/or `listen_on`) is in kitty.conf
  is enough signal — next startup re-evaluates the state machine,
  finds the directives present, skips the modal naturally. No need
  to also remember "we showed this once".

- **Comment format `# ztc:<json>`, with merge-on-read +
  canonicalize-on-write**. JSON is parsed with `json.loads`, no
  custom parser. Strict prefix `^# ztc:` (single space) avoids
  accidental matches in user comments. Each key is one entry in
  the JSON object — single line, multiple keys possible if needed
  later (today only one). **Multiple `# ztc:` lines in the same
  file** (which can happen if the user edits manually or if a
  future bug ever leaves duplicates) are reconciled at read time
  by merging into one dict with last-wins per key, and at write
  time by deleting every `# ztc:` line and writing a single
  canonical line. The prefix is ZTC's namespace — dedupe is safe
  (no risk of clobbering unrelated user comments). Result: file
  is always normalized to a single `# ztc:` line after the next
  save.

- **Auto-recreate on accidental deletion**. If the user manually
  deletes the `# ztc:` line, ZTC treats it as never-asked on next
  startup and shows the modal again. The user reaffirms or dismisses
  — the choice is respected anew. No silent state corruption.

- **Restart-required is upfront**. The modal explicitly says "you
  need to restart Kitty for this to take effect". No hidden
  "configured but not active" state surprising the user.

- **DRY via full `save_with_reload()` helper, not just toast
  composition**. The Stage B logic introduces a *new sequence*:
  save → try reload → distinguish outcome → compose user-facing
  message. Centralizing only the message leaves the screens
  orchestrating the sequence and querying both `reload_after_save()`
  and `manual_reload_hint()` directly. With the full helper, screens
  reduce to "call helper, show toast, handle error". Two concrete
  wins: (a) screens never reference `reload_after_save()` or
  `manual_reload_hint()` directly — they only consume the
  `SaveResult` data shape; (b) test surface drops — `test_save_helper.py`
  covers the sequence once, screen tests just verify "consume
  result". (Note: the hint itself comes from the Protocol method
  `backend.manual_reload_hint()`, queried by the helper internally;
  see the file #1 entry and the Protocol-surface note above for
  why it lives in the Protocol rather than as a `dict` keyed by
  `backend.kind`.)

- **`subprocess.run` with timeout=2 and broad exception swallow**.
  Cheap call, fast failure. Stderr is captured (`capture_output=True`)
  but **not shown to the user** in the fallback toast — the toast
  stays clean with just the manual-reload hint. Captured stderr is
  available for future internal logging; not exposed in Stage B.
  Reload is opportunistic; any error in the attempt is caught
  broadly (`except Exception`) and converted to `False` — never
  propagates as a save error.

## Stage B out of scope

- **Reload triggered automatically when ZTC starts** (vs. only on
  save). Not needed — saves are the only state-changing events.
- **Setting `allow_remote_control no` via ZTC**. The reverse path
  (user wants to turn off remote control) stays manual. Out of
  scope.
- **Detecting if Kitty itself is running** (e.g., user might have
  kitty.conf set to `yes` but no Kitty instance). `kitty @
  load-config` fails gracefully in that case — same as the
  fallback path.
- **General-purpose ZTC preferences file**. We commit to the
  comment-in-kitty.conf approach for this single preference. If
  a future feature really needs cross-config-file state, that's
  a separate plan.

## Stage B acceptance criteria

- `uv run pytest -q` passes including new tests.
- `uv run ruff check` clean.
- Manual smoke test 1 (educational modal): user has Kitty backend
  with `allow_remote_control` not set and `listen_on` not set in
  kitty.conf, no `# ztc:` comment. Run ZTC → modal appears
  explaining the trade-off and mentioning both directives.
- Manual smoke test 2a (Enable path, both missing): from state of
  test 1, click "Enable" → kitty.conf gets both
  `allow_remote_control yes` and `listen_on unix:@ztc-{kitty_pid}`
  appended → toast "Added 2 lines... restart Kitty". Restart Kitty
  → run ZTC again → no modal.
- Manual smoke test 2b (Enable path, only listen_on missing):
  start with `allow_remote_control yes` set but no `listen_on`.
  Modal appears (auto-reload still won't work in Zellij). Click
  "Enable" → only `listen_on` appended → toast "Added 1 line".
  Restart Kitty → next run, no modal.
- Manual smoke test 2c (Enable path, only RC missing): start with
  `listen_on` set but `allow_remote_control no`. Modal appears.
  Click "Enable" → only `allow_remote_control yes` appended →
  toast "Added 1 line".
- Manual smoke test 3 (Skip + dismiss): in the modal, click "Skip"
  with checkbox marked → kitty.conf gets the `# ztc:` comment line
  → next ZTC run does not show the modal.
- Manual smoke test 4 (hybrid save success): with remote control
  active and reachable, save a color change from ZTC → toast
  matches `compose_save_toast` format ("Saved: kitty.conf  (backup:
  kitty.conf.bak)" — **no** manual-reload hint appended) → Kitty
  immediately renders the new color.
- Manual smoke test 5 (hybrid save fallback): with remote control
  disabled or unreachable, save a color change → toast format
  appends "Press Ctrl+Shift+F5 in Kitty to reload." on a new line
  → user reloads manually → color renders.
- Manual smoke test 6 (theme_sync hybrid): apply a different Zellij
  theme, triggering `sync_terminal_with_zellij_theme`. With reload
  reachable: theme appears in Kitty immediately; toast keeps its
  current format. With reload not reachable: toast still says theme
  was synced AND appends the reload hint.
- **Manual smoke test 7 (Kitty → Zellij → ZTC, BLOCKING)**: Real
  deployment scenario. With kitty.conf having both
  `allow_remote_control yes` and `listen_on unix:@ztc-{kitty_pid}`,
  restart Kitty fresh, launch Zellij in it, verify
  `echo $KITTY_LISTEN_ON` is non-empty inside a Zellij pane and
  shows the PID expanded (e.g. `unix:@ztc-12345`, with no literal
  `{kitty_pid}` token), launch `ztc` from inside Zellij. Save a
  color change. Expected: ZTC's `reload_after_save` invokes
  `kitty @ --to "$KITTY_LISTEN_ON" load-config`, succeeds, Kitty
  renders the new color immediately, toast format shows no
  manual-reload hint. **If this test fails after the redesign**,
  the socket path is also unreachable in the user's environment
  and Stage B regresses to manual-reload-only — fall back to
  acceptance test 5 (manual reload toast) and document the
  limitation.

  **Pre-redesign smoke test 7 results (preserved as historical
  record)**:
  - Phase 1 (Kitty alone, no Zellij, plain `kitty @ load-config`):
    OK.
  - Phase 2 (inside Zellij, plain `kitty @ load-config`): FAIL
    with "Error: i/o timeout" — confirmed Zellij intermediates
    the TTY-based remote control.
  - Phase 3 (`echo $KITTY_LISTEN_ON` outside Zellij after adding
    `listen_on unix:@kitty-${KITTY_PID}` and restart): non-empty,
    e.g. `unix:@kitty-${KITTY_PID}-1247432`.
  - Phase 4 (`echo $KITTY_LISTEN_ON` inside Zellij): same value
    as phase 3 → env var propagates.
  - Phase 5 (`kitty @ --to "$KITTY_LISTEN_ON" load-config` inside
    Zellij): OK → socket path bypasses the TTY-routing problem.
  These results validated the redesign from TTY-based (broken in
  Zellij) to socket-based (works in Zellij when env var is set).
- Alacritty paths continue to work with no regression and no
  unrelated UI changes.
