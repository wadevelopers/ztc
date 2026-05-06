from __future__ import annotations

from term_config_tui.services.runtime_detect import detect_terminal


def test_detect_alacritty_via_window_id() -> None:
    d = detect_terminal({"ALACRITTY_WINDOW_ID": "12345"})
    assert d.kind == "alacritty"
    assert d.via_ssh is False
    assert d.raw_marker == "env:ALACRITTY_WINDOW_ID"
    assert d.invalid_override_value is None


def test_detect_alacritty_via_socket() -> None:
    d = detect_terminal({"ALACRITTY_SOCKET": "/tmp/foo.sock"})
    assert d.kind == "alacritty"
    assert d.raw_marker == "env:ALACRITTY_SOCKET"


def test_detect_kitty_via_pid() -> None:
    d = detect_terminal({"KITTY_PID": "9876"})
    assert d.kind == "kitty"
    assert d.raw_marker == "env:KITTY_PID"


def test_detect_kitty_via_window_id() -> None:
    d = detect_terminal({"KITTY_WINDOW_ID": "1"})
    assert d.kind == "kitty"
    assert d.raw_marker == "env:KITTY_WINDOW_ID"


def test_detect_kitty_via_term() -> None:
    d = detect_terminal({"TERM": "xterm-kitty"})
    assert d.kind == "kitty"
    assert d.raw_marker == "TERM=xterm-kitty"


def test_detect_unsupported_for_unknown_term_program() -> None:
    d = detect_terminal({"TERM_PROGRAM": "iTerm.app"})
    assert d.kind == "unsupported"
    assert d.raw_marker == "TERM_PROGRAM=iTerm.app"


def test_detect_unsupported_for_empty_env() -> None:
    d = detect_terminal({})
    assert d.kind == "unsupported"
    assert d.raw_marker is None
    assert d.via_ssh is False


def test_detect_unsupported_for_only_TERM() -> None:
    d = detect_terminal({"TERM": "xterm-256color"})
    assert d.kind == "unsupported"
    assert d.raw_marker == "TERM=xterm-256color"


def test_detect_ssh_flag() -> None:
    d = detect_terminal(
        {"ALACRITTY_WINDOW_ID": "1", "SSH_CONNECTION": "1.2.3.4 22 5.6.7.8 22"}
    )
    assert d.kind == "alacritty"
    assert d.via_ssh is True


def test_detect_ssh_alone_unsupported() -> None:
    d = detect_terminal({"SSH_CONNECTION": "1.2.3.4 22 5.6.7.8 22"})
    assert d.kind == "unsupported"
    assert d.via_ssh is True


def test_override_alacritty_skips_autodetect() -> None:
    # Env de Kitty real, pero override fuerza Alacritty.
    d = detect_terminal({"KITTY_PID": "1", "TERM_CONFIG_TUI_BACKEND": "alacritty"})
    assert d.kind == "alacritty"
    assert d.raw_marker == "override:alacritty"


def test_override_kitty_skips_autodetect() -> None:
    d = detect_terminal({"ALACRITTY_WINDOW_ID": "1", "TERM_CONFIG_TUI_BACKEND": "kitty"})
    assert d.kind == "kitty"
    assert d.raw_marker == "override:kitty"


def test_override_auto_falls_through_to_autodetect() -> None:
    d = detect_terminal({"KITTY_PID": "1", "TERM_CONFIG_TUI_BACKEND": "auto"})
    assert d.kind == "kitty"
    assert d.raw_marker == "env:KITTY_PID"


def test_override_empty_string_falls_through() -> None:
    d = detect_terminal({"KITTY_PID": "1", "TERM_CONFIG_TUI_BACKEND": ""})
    assert d.kind == "kitty"
    assert d.raw_marker == "env:KITTY_PID"


def test_override_invalid_value_marks_unsupported() -> None:
    d = detect_terminal({"TERM_CONFIG_TUI_BACKEND": "potato"})
    assert d.kind == "unsupported"
    assert d.invalid_override_value == "potato"
    assert d.raw_marker == "override:potato"


def test_override_invalid_value_overrides_real_env() -> None:
    """Aunque la env real sea kitty, override invalido deshabilita."""
    d = detect_terminal({"KITTY_PID": "1", "TERM_CONFIG_TUI_BACKEND": "wezterm"})
    assert d.kind == "unsupported"
    assert d.invalid_override_value == "wezterm"


def test_override_ghostty_is_invalid_in_phase_b() -> None:
    """Ghostty esta diferida (Fase D), no esta en VALID_OVERRIDE_KINDS."""
    d = detect_terminal({"TERM_CONFIG_TUI_BACKEND": "ghostty"})
    assert d.kind == "unsupported"
    assert d.invalid_override_value == "ghostty"
