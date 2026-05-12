from __future__ import annotations

from types import SimpleNamespace

from ztc.services import fonts


def test_resolve_font_faces_falls_back_to_regular(monkeypatch) -> None:
    monkeypatch.setattr(fonts.shutil, "which", lambda name: "/usr/bin/fc-list")
    monkeypatch.setattr(
        fonts.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="C64 Pro Mono:style=Regular\n",
        ),
    )

    faces = fonts.resolve_font_faces("C64 Pro Mono")

    assert faces.normal.style == "Regular"
    assert faces.bold.style == "Regular"
    assert faces.bold.fallback is True
    assert faces.italic.style == "Regular"
    assert faces.italic.fallback is True
    assert faces.bold_italic.style == "Regular"
    assert faces.bold_italic.fallback is True


def test_resolve_font_faces_uses_available_styles(monkeypatch) -> None:
    monkeypatch.setattr(fonts.shutil, "which", lambda name: "/usr/bin/fc-list")
    monkeypatch.setattr(
        fonts.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=(
                "DejaVu Sans Mono:style=Book\n"
                "DejaVu Sans Mono:style=Bold\n"
                "DejaVu Sans Mono:style=Oblique\n"
                "DejaVu Sans Mono:style=Bold Oblique\n"
            ),
        ),
    )

    faces = fonts.resolve_font_faces("DejaVu Sans Mono")

    assert faces.normal.style == "Book"
    assert faces.bold.style == "Bold"
    assert faces.italic.style == "Oblique"
    assert faces.bold_italic.style == "Bold Oblique"
    assert faces.bold.fallback is False
    assert faces.italic.fallback is False
    assert faces.bold_italic.fallback is False
