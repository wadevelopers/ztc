"""Tests del helper list_monospace_fonts (fontconfig wrapper)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ztc.services.fonts import list_monospace_fonts


def test_returns_empty_when_fc_list_missing() -> None:
    with patch("ztc.services.fonts.shutil.which", return_value=None):
        assert list_monospace_fonts() == []


def test_parses_primary_alias_only() -> None:
    """Output como `JetBrainsMono Nerd Font,JetBrainsMono NF,JetBrainsMono NF Bold`
    debe quedar como `JetBrainsMono Nerd Font` (primer alias)."""
    fake_stdout = (
        "JetBrainsMono Nerd Font,JetBrainsMono NF,JetBrainsMono NF Bold\n"
        "DejaVu Sans Mono\n"
        "JetBrainsMono Nerd Font,JetBrainsMono NF,JetBrainsMono NF ExtraLight\n"
        "Courier New\n"
    )
    fake_proc = MagicMock(returncode=0, stdout=fake_stdout)
    with (
        patch("ztc.services.fonts.shutil.which", return_value="/usr/bin/fc-list"),
        patch("ztc.services.fonts.subprocess.run", return_value=fake_proc),
    ):
        fonts = list_monospace_fonts()
    # Deduplicado y ordenado.
    assert fonts == [
        "Courier New",
        "DejaVu Sans Mono",
        "JetBrainsMono Nerd Font",
    ]


def test_returns_empty_on_nonzero_exit() -> None:
    fake_proc = MagicMock(returncode=1, stdout="")
    with (
        patch("ztc.services.fonts.shutil.which", return_value="/usr/bin/fc-list"),
        patch("ztc.services.fonts.subprocess.run", return_value=fake_proc),
    ):
        assert list_monospace_fonts() == []


def test_returns_empty_on_timeout() -> None:
    import subprocess

    with (
        patch("ztc.services.fonts.shutil.which", return_value="/usr/bin/fc-list"),
        patch(
            "ztc.services.fonts.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["fc-list"], timeout=5),
        ),
    ):
        assert list_monospace_fonts() == []


def test_skips_blank_lines_and_whitespace() -> None:
    fake_stdout = "  Andale Mono  \n\n   \nConsolas\n,empty alias\n"
    fake_proc = MagicMock(returncode=0, stdout=fake_stdout)
    with (
        patch("ztc.services.fonts.shutil.which", return_value="/usr/bin/fc-list"),
        patch("ztc.services.fonts.subprocess.run", return_value=fake_proc),
    ):
        fonts = list_monospace_fonts()
    # "Andale Mono" trim, "Consolas" presente, ",empty alias" → "" se filtra,
    # pero la palabra "empty alias" tras la coma no se considera (solo el primer alias).
    assert "Andale Mono" in fonts
    assert "Consolas" in fonts
    # "" no esta porque se filtra.
    assert "" not in fonts
